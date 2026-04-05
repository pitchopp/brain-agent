"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from brain_agent.agent.auth import log_auth_status
from brain_agent.brain import repo
from brain_agent.brain.puller import run_puller
from brain_agent.config import get_settings
from brain_agent.telegram.webhook import router as telegram_router


def _setup_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    logger = logging.getLogger("brain_agent.main")
    logger.info("brain-agent starting up")

    log_auth_status(get_settings().anthropic_api_key or None)

    repo.setup_ssh_key()
    await repo.configure_git_identity()
    await repo.ensure_brain_cloned()

    puller_task = asyncio.create_task(run_puller())
    try:
        yield
    finally:
        logger.info("brain-agent shutting down")
        puller_task.cancel()
        try:
            await puller_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="brain-agent", lifespan=lifespan)
app.include_router(telegram_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
