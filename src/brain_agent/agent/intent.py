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

# Strong capture signals: affirmations, updates, corrections. If any of these
# substrings appears anywhere in the text, we force capture even if the message
# happens to end with a question mark.
CAPTURE_MARKERS: tuple[str, ...] = (
    "en fait",
    "en vrai",
    "note que",
    "ajoute que",
    "ajoute ça",
    "ajoute ca",
    "retiens que",
    "retiens ça",
    "retiens ca",
    "enregistre",
    "sauvegarde",
    "mémorise",
    "memorise",
    "mets à jour",
    "mets a jour",
    "corrige",
    "rectif",
    "update",
    "save this",
)


def detect_intent(text: str) -> Intent:
    """Route text to either 'capture' (write) or 'query' (read)."""
    t = text.strip().lower()
    if not t:
        return "capture"
    # Explicit prefixes always win.
    if t.startswith("?"):
        return "query"
    if t.startswith("!"):
        return "capture"
    # Strong capture markers override everything except explicit "?" prefix.
    if any(marker in t for marker in CAPTURE_MARKERS):
        return "capture"
    if t.endswith("?"):
        return "query"
    if any(t.startswith(w) for w in INTERROGATIVES):
        return "query"
    return "capture"
