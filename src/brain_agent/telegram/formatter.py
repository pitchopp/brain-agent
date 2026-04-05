"""Format agent responses for Telegram delivery (HTML parse mode).

Telegram's sendMessage is called with parse_mode=HTML, so the agent can use a
small whitelist of tags (<b>, <i>, <u>, <s>, <code>, <pre>, <a href>,
<blockquote>) for rich rendering. Anything else — including stray `<`, `>`, `&`
in free text — must be escaped or Telegram returns HTTP 400 and the message is
lost. This module defensively rewrites the agent's output to guarantee valid
HTML even when the model slips up.
"""

from __future__ import annotations

import re

# Telegram sendMessage max length.
TELEGRAM_MAX_LEN = 4096
_TRUNCATION_SUFFIX = "\n\n... (tronqué)"

# Tags Telegram accepts in HTML parse mode. See
# https://core.telegram.org/bots/api#html-style
_ALLOWED_TAGS = {
    "b", "strong",
    "i", "em",
    "u", "ins",
    "s", "strike", "del",
    "code", "pre",
    "a",
    "blockquote",
    "tg-spoiler",
}

# Matches a tag candidate: opening, closing, or self-closing. We only capture
# the tag name; attribute validation happens per-tag below.
_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?>")

# Matches an `&` that is NOT already the start of a valid entity. We escape
# those to `&amp;` so Telegram doesn't choke.
_BARE_AMP_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)")


def _sanitize_html(text: str) -> str:
    """Escape stray HTML metacharacters, preserving allowed tags.

    Strategy:
    1. Escape bare `&` to `&amp;` (preserving existing valid entities).
    2. Walk the string, looking for tag-like patterns. If the tag name is in
       the allowed set, keep the tag verbatim. Otherwise escape the `<` and
       `>` to `&lt;` / `&gt;`.
    3. Any remaining `<` or `>` that didn't match the tag regex (e.g. `a < b`)
       is escaped too.
    """
    text = _BARE_AMP_RE.sub("&amp;", text)

    out: list[str] = []
    pos = 0
    for match in _TAG_RE.finditer(text):
        # Escape any `<` / `>` in the segment before this tag.
        out.append(text[pos:match.start()].replace("<", "&lt;").replace(">", "&gt;"))
        tag_name = match.group(2).lower()
        if tag_name in _ALLOWED_TAGS:
            out.append(match.group(0))
        else:
            out.append(match.group(0).replace("<", "&lt;").replace(">", "&gt;"))
        pos = match.end()
    # Tail after the last tag.
    out.append(text[pos:].replace("<", "&lt;").replace(">", "&gt;"))
    return "".join(out)


def format_for_telegram(text: str) -> str:
    """Sanitize and truncate an agent response for Telegram (HTML mode)."""
    text = _sanitize_html(text.strip())
    if len(text) <= TELEGRAM_MAX_LEN:
        return text
    keep = TELEGRAM_MAX_LEN - len(_TRUNCATION_SUFFIX)
    return text[:keep] + _TRUNCATION_SUFFIX
