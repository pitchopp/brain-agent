"""Tests for auth resolution (OAuth vs API key)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from brain_agent.agent import auth


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write_creds(home: Path, *, refresh: str, expires_at: int | None) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir()
    payload = {
        "claudeAiOauth": {
            "accessToken": "a-token",
            "refreshToken": refresh,
            "expiresAt": expires_at,
            "scopes": ["user:inference"],
            "subscriptionType": "max",
        }
    }
    (claude_dir / ".credentials.json").write_text(json.dumps(payload))


def test_oauth_preferred_over_api_key(fake_home: Path) -> None:
    future_ms = int(time.time() * 1000) + 3_600_000
    _write_creds(fake_home, refresh="r-token", expires_at=future_ms)

    resolved = auth.resolve_auth("sk-test-key")

    assert resolved.mode == "oauth"
    # Critically, ANTHROPIC_API_KEY must NOT be passed when OAuth is used,
    # otherwise the CLI would prefer it and bill against the API.
    assert resolved.env == {}


def test_oauth_still_used_when_access_token_expired(fake_home: Path) -> None:
    past_ms = int(time.time() * 1000) - 60_000
    _write_creds(fake_home, refresh="r-token", expires_at=past_ms)

    resolved = auth.resolve_auth("sk-test-key")

    # Expired access token is fine — the CLI refreshes it via refreshToken.
    assert resolved.mode == "oauth"


def test_fallback_to_api_key_when_no_oauth(fake_home: Path) -> None:
    resolved = auth.resolve_auth("sk-test-key")

    assert resolved.mode == "api_key"
    assert resolved.env == {"ANTHROPIC_API_KEY": "sk-test-key"}


def test_fallback_when_oauth_file_has_no_refresh_token(fake_home: Path) -> None:
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir()
    (claude_dir / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "x"}})
    )

    resolved = auth.resolve_auth("sk-test-key")

    assert resolved.mode == "api_key"


def test_fallback_when_oauth_file_is_invalid_json(fake_home: Path) -> None:
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir()
    (claude_dir / ".credentials.json").write_text("{not json")

    resolved = auth.resolve_auth("sk-test-key")

    assert resolved.mode == "api_key"


def test_raises_when_no_auth_available(fake_home: Path) -> None:
    with pytest.raises(RuntimeError, match="No auth available"):
        auth.resolve_auth(None)


def test_raises_when_only_empty_api_key(fake_home: Path) -> None:
    with pytest.raises(RuntimeError, match="No auth available"):
        auth.resolve_auth("")
