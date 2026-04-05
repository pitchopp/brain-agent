"""Telegram webhook endpoint."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from brain_agent.agent.runner import run_turn
from brain_agent.config import get_settings
from brain_agent.telegram import client as tg
from brain_agent.telegram.formatter import format_for_telegram

logger = logging.getLogger(__name__)
router = APIRouter()

# Track update_ids we've already accepted, so Telegram retries (same update
# re-delivered because we didn't 200 fast enough, or because Dokploy restarted)
# are silently dropped instead of spawning a second agent instance.
_seen_update_ids: set[int] = set()
_SEEN_MAX = 1024

# Per-chat serialization: only one agent turn runs at a time per chat_id.
# Additional messages queue up behind the lock in arrival order.
_chat_locks: dict[int, asyncio.Lock] = {}


def _mark_seen(update_id: int) -> bool:
    """Return True if this update_id is new, False if already seen."""
    if update_id in _seen_update_ids:
        return False
    _seen_update_ids.add(update_id)
    if len(_seen_update_ids) > _SEEN_MAX:
        # Drop oldest ~half. Set ordering is insertion order in CPython 3.7+.
        for old in list(_seen_update_ids)[: _SEEN_MAX // 2]:
            _seen_update_ids.discard(old)
    return True


def _get_chat_lock(chat_id: int) -> asyncio.Lock:
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock


async def _process_update(chat_id: int, text: str) -> None:
    """Run one agent turn and stream its output to Telegram.

    Runs as a background task so the webhook can return 200 immediately and
    avoid Telegram retries on long turns. Per-chat serialization ensures only
    one turn runs at a time per chat: additional messages queue up and are
    processed in arrival order. Enforces a hard timeout: when it fires, the
    run_turn task is cancelled, which propagates through
    ClaudeSDKClient.__aexit__ and kills the bundled `claude` subprocess.
    """
    settings = get_settings()
    lock = _get_chat_lock(chat_id)

    # If the agent is already busy for this chat, tell the user their message
    # is queued before we block on the lock.
    if lock.locked():
        try:
            await tg.send_message(
                chat_id,
                "⏳ Je termine ton message précédent, je m'occupe de celui-ci juste après.",
            )
        except Exception:
            logger.exception("failed to send queued notice")

    async with lock:
        try:
            await tg.send_chat_action(chat_id, "typing")
        except Exception:
            logger.exception("failed to send typing action")

        chunks_sent = 0

        async def send_chunk(chunk: str) -> None:
            nonlocal chunks_sent
            try:
                await tg.send_message(chat_id, format_for_telegram(chunk))
                chunks_sent += 1
            except Exception:
                logger.exception("failed to send streamed chunk to Telegram")
            try:
                await tg.send_chat_action(chat_id, "typing")
            except Exception:
                pass

        turn_task = asyncio.create_task(run_turn(text, on_chunk=send_chunk))
        try:
            await asyncio.wait_for(
                asyncio.shield(turn_task), timeout=settings.agent_timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning(
                "agent timeout after %ss — cancelling", settings.agent_timeout_seconds
            )
            turn_task.cancel()
            # Wait for the task to fully tear down (SDK subprocess kill). We give
            # it a short grace window; if it refuses to die we move on — but we do
            # NOT send any further messages either way.
            try:
                await asyncio.wait_for(turn_task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
            try:
                if chunks_sent == 0:
                    await tg.send_message(
                        chat_id,
                        "⏱ Trop long, j'ai abandonné. Réessaye avec une demande plus simple.",
                    )
                else:
                    await tg.send_message(chat_id, "⏱ (timeout atteint, je m'arrête ici)")
            except Exception:
                logger.exception("failed to send timeout message")
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent error")
            try:
                await tg.send_message(
                    chat_id, f"❌ Erreur interne : {type(exc).__name__}: {exc}"
                )
            except Exception:
                logger.exception("failed to send error message")


@router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = get_settings()

    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        logger.warning("rejected webhook: bad secret")
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        update = await request.json()
    except Exception:
        logger.warning("rejected webhook: invalid JSON body")
        raise HTTPException(status_code=400, detail="invalid json")

    update_id = update.get("update_id")
    if isinstance(update_id, int) and not _mark_seen(update_id):
        logger.info("dropping duplicate update_id=%s", update_id)
        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}
    text = message.get("text")
    if not text:
        return {"ok": True}

    from_user = message.get("from", {})
    user_id = from_user.get("id")
    if user_id is None:
        return {"ok": True}

    allowed = settings.allowed_user_ids_set
    if not allowed or user_id not in allowed:
        logger.warning("rejected user_id=%s (not whitelisted)", user_id)
        return {"ok": True}  # silent drop

    chat_id = message["chat"]["id"]

    # Fire-and-forget: return 200 immediately so Telegram does not retry.
    asyncio.create_task(_process_update(chat_id, text))
    return {"ok": True}
