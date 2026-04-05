"""Git repository management for the brain working copy.

Wraps the `git` binary via asyncio subprocess. Exposes an async lock that
must be held by any code reading or writing the working tree concurrently.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from brain_agent.config import get_settings

logger = logging.getLogger(__name__)

# Single global lock. The puller, the agent runner and the git_commit_push
# tool all acquire it before touching the working tree.
repo_lock = asyncio.Lock()


@dataclass
class GitResult:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


async def run_git(*args: str, cwd: Path | None = None) -> GitResult:
    """Run a git command and return its result. Does NOT acquire the lock."""
    settings = get_settings()
    working = cwd or settings.brain_local_path
    env = os.environ.copy()
    # Make sure git uses our SSH key if provided.
    ssh_key_path = Path.home() / ".ssh" / "id_ed25519"
    if ssh_key_path.exists():
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null"
        )
    logger.debug("git %s (cwd=%s)", " ".join(args), working)
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(working) if working.exists() else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return GitResult(
        code=proc.returncode or 0,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


def setup_ssh_key() -> None:
    """Write the SSH private key from env into ~/.ssh/id_ed25519.

    Also writes ~/.ssh/config so that any `git push` (including ones issued by
    the agent via the Bash tool, which bypass our GIT_SSH_COMMAND) skips host
    key verification. No-op if the key env var is empty.
    """
    settings = get_settings()
    if not settings.git_ssh_private_key.strip():
        logger.info("No GIT_SSH_PRIVATE_KEY provided, skipping SSH key setup")
        return
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key_path = ssh_dir / "id_ed25519"
    key_content = settings.git_ssh_private_key
    if not key_content.endswith("\n"):
        key_content += "\n"
    key_path.write_text(key_content)
    key_path.chmod(0o600)
    logger.info("SSH key written to %s", key_path)

    config_path = ssh_dir / "config"
    config_path.write_text(
        "Host *\n"
        "    StrictHostKeyChecking no\n"
        "    UserKnownHostsFile /dev/null\n"
        "    IdentityFile ~/.ssh/id_ed25519\n"
        "    LogLevel ERROR\n"
    )
    config_path.chmod(0o600)
    logger.info("SSH config written to %s", config_path)


async def configure_git_identity() -> None:
    settings = get_settings()
    await run_git("config", "--global", "user.name", settings.git_user_name)
    await run_git("config", "--global", "user.email", settings.git_user_email)
    await run_git("config", "--global", "pull.rebase", "true")


async def ensure_brain_cloned() -> None:
    """Clone the brain repo at startup if the working copy is empty."""
    settings = get_settings()
    path = settings.brain_local_path
    path.parent.mkdir(parents=True, exist_ok=True)

    git_dir = path / ".git"
    if git_dir.exists():
        logger.info("Brain already cloned at %s, pulling", path)
        async with repo_lock:
            res = await run_git("pull", "--rebase", "origin", settings.brain_repo_branch)
            if not res.ok:
                logger.error("Initial pull failed: %s", res.stderr)
        return

    logger.info("Cloning brain from %s to %s", settings.brain_repo_url, path)
    if path.exists() and any(path.iterdir()):
        raise RuntimeError(
            f"BRAIN_LOCAL_PATH {path} exists and is not empty but has no .git. "
            "Refusing to clobber."
        )
    path.mkdir(exist_ok=True)
    res = await run_git(
        "clone",
        "--branch",
        settings.brain_repo_branch,
        settings.brain_repo_url,
        str(path),
        cwd=path.parent,
    )
    if not res.ok:
        raise RuntimeError(f"git clone failed: {res.stderr}")
    logger.info("Brain cloned successfully")


async def pull_rebase() -> GitResult:
    """Pull with rebase. Caller must hold repo_lock."""
    settings = get_settings()
    return await run_git("pull", "--rebase", "origin", settings.brain_repo_branch)


async def commit_and_push(message: str) -> tuple[bool, str]:
    """Stage, commit, push. Returns (success, info).

    Caller must hold repo_lock.
    """
    settings = get_settings()

    status = await run_git("status", "--porcelain")
    if not status.stdout.strip():
        return False, "no changes to commit"

    add = await run_git("add", "-A")
    if not add.ok:
        return False, f"git add failed: {add.stderr}"

    commit = await run_git("commit", "-m", message)
    if not commit.ok:
        return False, f"git commit failed: {commit.stderr}"

    # Grab short SHA.
    rev = await run_git("rev-parse", "--short", "HEAD")
    sha = rev.stdout.strip()

    push = await run_git("push", "origin", settings.brain_repo_branch)
    if not push.ok:
        return False, f"git push failed: {push.stderr}"

    return True, sha
