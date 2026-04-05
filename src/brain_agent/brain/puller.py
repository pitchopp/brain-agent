"""Background task: periodically rebase the local brain on origin."""

from __future__ import annotations

import asyncio
import logging

from brain_agent.brain import repo
from brain_agent.config import get_settings
from brain_agent.telegram import client as tg

logger = logging.getLogger(__name__)


async def run_puller() -> None:
    settings = get_settings()
    interval = settings.brain_pull_interval_seconds
    logger.info("puller started, interval=%ss", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            async with repo.repo_lock:
                res = await repo.pull_rebase()
            if not res.ok:
                combined = (res.stdout + res.stderr).lower()
                if "conflict" in combined or "could not apply" in combined:
                    logger.error("git conflict during pull: %s", res.stderr)
                    try:
                        await tg.notify_admin(
                            "⚠️ conflit git détecté sur le brain, rebase manuel nécessaire.\n"
                            f"stderr:\n{res.stderr[:500]}"
                        )
                    except Exception:
                        logger.exception("failed to notify admin about git conflict")
                else:
                    logger.warning("pull failed: %s", res.stderr)
        except asyncio.CancelledError:
            logger.info("puller cancelled")
            raise
        except Exception:
            logger.exception("puller iteration failed")
