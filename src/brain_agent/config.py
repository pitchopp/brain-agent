"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(..., alias="TELEGRAM_WEBHOOK_SECRET")
    allowed_telegram_user_ids: str = Field("", alias="ALLOWED_TELEGRAM_USER_IDS")
    telegram_admin_chat_id: int | None = Field(None, alias="TELEGRAM_ADMIN_CHAT_ID")

    # Anthropic — either an API key OR an OAuth session (preferred, cheaper).
    # At least one of the two must be available at runtime (see agent.auth).
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-sonnet-4-5", alias="ANTHROPIC_MODEL")

    # Git / brain repo
    brain_repo_url: str = Field(..., alias="BRAIN_REPO_URL")
    brain_repo_branch: str = Field("main", alias="BRAIN_REPO_BRANCH")
    brain_local_path: Path = Field(Path("/data/brain"), alias="BRAIN_LOCAL_PATH")
    git_user_name: str = Field("brain-agent", alias="GIT_USER_NAME")
    git_user_email: str = Field("brain-agent@local", alias="GIT_USER_EMAIL")
    git_ssh_private_key: str = Field("", alias="GIT_SSH_PRIVATE_KEY")

    # Runtime
    brain_pull_interval_seconds: int = Field(300, alias="BRAIN_PULL_INTERVAL_SECONDS")
    max_agent_turns: int = Field(40, alias="MAX_AGENT_TURNS")
    agent_timeout_seconds: int = Field(300, alias="AGENT_TIMEOUT_SECONDS")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("allowed_telegram_user_ids")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def allowed_user_ids_set(self) -> set[int]:
        if not self.allowed_telegram_user_ids:
            return set()
        return {
            int(part.strip())
            for part in self.allowed_telegram_user_ids.split(",")
            if part.strip()
        }


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
