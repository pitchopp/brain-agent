"""Agent runner: wires the Claude Agent SDK to the brain and executes a single turn."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    TextBlock,
    ToolPermissionContext,
)

from brain_agent.agent.intent import detect_intent
from brain_agent.agent.prompt import build_system_prompt
from brain_agent.brain import repo
from brain_agent.config import get_settings
from brain_agent.tools.brain_mcp import brain_mcp_server

logger = logging.getLogger(__name__)

OnChunk = Callable[[str], Awaitable[None]]

BUILTIN_TOOLS = ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
MCP_TOOLS = [
    "mcp__brain__validate_brain",
    "mcp__brain__git_commit_push",
]
ALLOWED_TOOLS = BUILTIN_TOOLS + MCP_TOOLS


async def _auto_approve_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResultAllow:
    """Auto-approve any tool in the allowlist.

    The agent runs headless behind a Telegram webhook with no human to approve
    tool calls interactively. We cannot use permission_mode="bypassPermissions"
    because the bundled Claude Code CLI refuses it when running as root inside
    the container, so we provide an explicit can_use_tool handler instead.
    """
    logger.debug("auto-approving tool %s", tool_name)
    return PermissionResultAllow()


async def run_turn(user_text: str, on_chunk: OnChunk | None = None) -> str:
    """Execute one exchange with the agent.

    Streams intermediate assistant messages via `on_chunk` as the agent
    produces them (one call per non-empty AssistantMessage text). Returns
    the concatenated full response at the end.
    """
    settings = get_settings()
    intent = detect_intent(user_text)
    logger.info("intent=%s text=%r", intent, user_text)

    # In capture mode, always pull first so the agent works from a fresh state.
    if intent == "capture":
        async with repo.repo_lock:
            res = await repo.pull_rebase()
            if not res.ok:
                logger.warning("pre-turn pull failed: %s", res.stderr)

    system_prompt = build_system_prompt(
        intent, settings.brain_local_path, settings.max_agent_turns
    )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=settings.anthropic_model,
        allowed_tools=ALLOWED_TOOLS,
        mcp_servers={"brain": brain_mcp_server},
        cwd=str(settings.brain_local_path),
        permission_mode="default",
        can_use_tool=_auto_approve_tool,
        max_turns=settings.max_agent_turns,
        env={"ANTHROPIC_API_KEY": settings.anthropic_api_key},
    )

    full_response = ""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_text)
        async for message in client.receive_response():
            if not isinstance(message, AssistantMessage):
                continue
            chunk = "".join(
                block.text for block in message.content if isinstance(block, TextBlock)
            ).strip()
            if not chunk:
                continue
            full_response += ("\n\n" if full_response else "") + chunk
            if on_chunk is not None:
                try:
                    await on_chunk(chunk)
                except Exception:
                    logger.exception("on_chunk callback failed")

    full_response = full_response.strip()
    if not full_response:
        full_response = "(l'agent n'a produit aucune réponse textuelle)"
    logger.info("agent response:\n%s", full_response)
    return full_response
