"""Authentication resolution for the bundled Claude Code CLI.

The CLI supports two auth modes:

1. OAuth session — credentials stored in `~/.claude/.credentials.json`. This
   is what a logged-in `claude` on a dev machine uses, and it bills against
   the user's Claude Max/Pro subscription instead of the API. Much cheaper.
2. `ANTHROPIC_API_KEY` env var — pay-per-token API billing.

We prefer OAuth when available and fall back to the API key otherwise. The
decision is made at runtime so the same image can run either way depending
on which secrets are mounted/injected.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedAuth:
    mode: str  # "oauth" | "api_key"
    env: dict[str, str]


def _credentials_path() -> Path:
    """Path to the CLI's OAuth credentials file, honoring $HOME."""
    return Path(os.path.expanduser("~/.claude/.credentials.json"))


def _oauth_available() -> bool:
    """Return True if a usable OAuth session exists on disk.

    "Usable" = the file is readable JSON with a non-empty refreshToken. We do
    NOT hard-fail on an expired accessToken because the CLI transparently
    refreshes it using the refreshToken; we only log a hint if the access
    token is already past its expiry so operators know a refresh will occur.
    """
    path = _credentials_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("OAuth credentials file unreadable (%s): %s", path, exc)
        return False

    oauth = data.get("claudeAiOauth") or {}
    refresh = oauth.get("refreshToken")
    if not refresh:
        logger.warning("OAuth credentials file present but has no refreshToken")
        return False

    expires_at = oauth.get("expiresAt")
    if isinstance(expires_at, int):
        now_ms = int(time.time() * 1000)
        if expires_at < now_ms:
            logger.info(
                "OAuth access token expired (expiresAt=%s, now=%s), CLI will refresh",
                expires_at,
                now_ms,
            )
    return True


def resolve_auth(api_key: str | None) -> ResolvedAuth:
    """Pick OAuth if available, otherwise fall back to the API key.

    Raises RuntimeError if neither is usable — we refuse to start the agent
    without any working auth, since the CLI would fail on every turn.
    """
    if _oauth_available():
        logger.info("using Claude OAuth session from %s", _credentials_path())
        # IMPORTANT: do NOT pass ANTHROPIC_API_KEY. If it is set, the CLI
        # prefers it over the OAuth session and we lose the cost benefit.
        return ResolvedAuth(mode="oauth", env={})

    if api_key:
        logger.info("using ANTHROPIC_API_KEY (no OAuth session found)")
        return ResolvedAuth(mode="api_key", env={"ANTHROPIC_API_KEY": api_key})

    raise RuntimeError(
        "No auth available: neither ~/.claude/.credentials.json nor "
        "ANTHROPIC_API_KEY is set. Mount an OAuth session or provide an API key."
    )


def log_auth_status(api_key: str | None) -> None:
    """Log the auth mode at startup so operators can verify the mount worked.

    Safe to call before the first turn; does not raise if nothing is
    configured, just logs a warning.
    """
    path = _credentials_path()
    if _oauth_available():
        logger.info("auth: OAuth session detected at %s (will be used)", path)
        if api_key:
            logger.info(
                "auth: ANTHROPIC_API_KEY is also set but will be ignored in favor of OAuth"
            )
        return
    if path.exists():
        logger.warning(
            "auth: %s exists but is unusable (bad JSON or missing refreshToken)",
            path,
        )
    else:
        logger.info("auth: no OAuth session at %s", path)
    if api_key:
        logger.info("auth: will fall back to ANTHROPIC_API_KEY")
    else:
        logger.warning(
            "auth: neither OAuth nor ANTHROPIC_API_KEY available — agent turns will fail"
        )
