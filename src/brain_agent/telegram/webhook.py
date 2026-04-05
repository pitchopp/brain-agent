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


@router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = get_settings()

    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        logger.warning("rejected webhook: bad secret")
        raise HTTPException(status_code=403, detail="forbidden")

    update = await request.json()
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

    try:
        await tg.send_chat_action(chat_id, "typing")
    except Exception:
        logger.exception("failed to send typing action")

    try:
        response = await asyncio.wait_for(
            run_turn(text),
            timeout=settings.agent_timeout_seconds,
        )
    except asyncio.TimeoutError:
        response = "⏱ Trop long, j'ai abandonné. Réessaye avec une demande plus simple."
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent error")
        response = f"❌ Erreur interne : {type(exc).__name__}: {exc}"

    try:
        await tg.send_message(chat_id, format_for_telegram(response))
    except Exception:
        logger.exception("failed to send response to Telegram")

    return {"ok": True}
