"""In-process MCP server exposing brain-specific tools to the Claude Agent SDK.

Tools:
    - validate_brain: run all validators, report errors.
    - git_commit_push: validate, then commit & push to origin.
"""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from brain_agent.brain import repo
from brain_agent.brain.validation import validate_all
from brain_agent.config import get_settings

logger = logging.getLogger(__name__)


def _text_response(text: str, is_error: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        payload["isError"] = True
    return payload


@tool(
    "validate_brain",
    "Valide que le brain respecte les contrats : wiki-links, tags de TAXONOMIE, "
    "et schéma de frontmatter. À appeler après chaque écriture avant de commit.",
    {},
)
async def validate_brain_tool(args: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    errors = validate_all(settings.brain_local_path)
    if not errors:
        return _text_response("✅ brain valide (0 erreur)")
    lines = [f"❌ {len(errors)} erreur(s) détectée(s) :"]
    for err in errors[:50]:
        lines.append(f"  - [{err.kind}] {err.file}: {err.detail}")
    if len(errors) > 50:
        lines.append(f"  ... et {len(errors) - 50} autres")
    return _text_response("\n".join(lines), is_error=True)


@tool(
    "git_commit_push",
    "Valide le brain, puis commit tous les changements avec le message fourni "
    "et push sur origin/main. Refuse si la validation échoue. "
    "Message de commit : suivre les conventions du brain (ex: "
    "'feat(knowledge): add principe-levier', 'chore(map): update index').",
    {"message": str},
)
async def git_commit_push_tool(args: dict[str, Any]) -> dict[str, Any]:
    message = args.get("message", "").strip()
    if not message:
        return _text_response("❌ message de commit vide", is_error=True)

    settings = get_settings()
    errors = validate_all(settings.brain_local_path)
    if errors:
        lines = [f"❌ validation échouée ({len(errors)} erreur(s)), commit refusé :"]
        for err in errors[:20]:
            lines.append(f"  - [{err.kind}] {err.file}: {err.detail}")
        return _text_response("\n".join(lines), is_error=True)

    async with repo.repo_lock:
        ok, info = await repo.commit_and_push(message)
    if not ok:
        return _text_response(f"❌ {info}", is_error=True)
    return _text_response(f"✅ commit {info} pushé sur origin/{settings.brain_repo_branch}")


# Create the MCP server once at import time. It will be referenced from runner.py.
brain_mcp_server = create_sdk_mcp_server(
    name="brain",
    version="0.1.0",
    tools=[validate_brain_tool, git_commit_push_tool],
)
