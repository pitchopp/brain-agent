"""Format agent responses for Telegram delivery."""

from __future__ import annotations

# Telegram sendMessage max length.
TELEGRAM_MAX_LEN = 4096
_TRUNCATION_SUFFIX = "\n\n... (tronqué)"


def format_for_telegram(text: str) -> str:
    """Clean and truncate an agent response for Telegram plain text."""
    text = text.strip()
    if len(text) <= TELEGRAM_MAX_LEN:
        return text
    keep = TELEGRAM_MAX_LEN - len(_TRUNCATION_SUFFIX)
    return text[:keep] + _TRUNCATION_SUFFIX
