"""Deterministic intent routing between capture and query."""

from __future__ import annotations

from typing import Literal

Intent = Literal["capture", "query"]

INTERROGATIVES: tuple[str, ...] = (
    "qu'est-ce",
    "que ",
    "qui ",
    "où ",
    "ou ",
    "quand ",
    "comment ",
    "pourquoi ",
    "combien ",
    "est-ce que ",
    "est-ce qu'",
    "quel ",
    "quelle ",
    "quels ",
    "quelles ",
    "cherche ",
    "trouve ",
    "résume ",
    "resume ",
    "liste ",
    "donne-moi ",
    "what ",
    "where ",
    "when ",
    "how ",
    "why ",
)


def detect_intent(text: str) -> Intent:
    """Route text to either 'capture' (write) or 'query' (read)."""
    t = text.strip().lower()
    if not t:
        return "capture"
    if t.startswith("?"):
        return "query"
    if t.startswith("!"):
        return "capture"
    if t.endswith("?"):
        return "query"
    if any(t.startswith(w) for w in INTERROGATIVES):
        return "query"
    return "capture"
