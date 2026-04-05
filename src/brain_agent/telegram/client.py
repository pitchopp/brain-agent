"""Minimal async Telegram Bot API client (httpx)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from brain_agent.config import get_settings

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"


async def _post(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = f"{_TELEGRAM_API}/bot{settings.telegram_bot_token}/{method}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        if r.status_code >= 400:
            logger.error("Telegram %s failed: %s %s", method, r.status_code, r.text)
        return r.json() if r.content else {}


async def send_message(chat_id: int, text: str, parse_mode: str | None = None) -> None:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    await _post("sendMessage", payload)


async def send_chat_action(chat_id: int, action: str = "typing") -> None:
    await _post("sendChatAction", {"chat_id": chat_id, "action": action})


async def notify_admin(text: str) -> None:
    settings = get_settings()
    if settings.telegram_admin_chat_id is None:
        logger.warning("no TELEGRAM_ADMIN_CHAT_ID set, skipping admin notify")
        return
    await send_message(settings.telegram_admin_chat_id, text)
