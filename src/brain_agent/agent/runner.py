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
    ToolUseBlock,
)

from brain_agent.agent.auth import resolve_auth
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

# Short progress pings shown in Telegram for capture mode (one per tool kind,
# deduplicated consecutively). Query mode stays silent until the final answer.
_TOOL_PINGS = {
    "Read": "je lis…",
    "Grep": "je cherche…",
    "Glob": "je cherche…",
    "Write": "j'écris…",
    "Edit": "j'édite…",
    "Bash": "j'exécute…",
    "mcp__brain__validate_brain": "je valide…",
    "mcp__brain__git_commit_push": "je commit…",
}


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

    auth = resolve_auth(settings.anthropic_api_key or None)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=settings.anthropic_model,
        allowed_tools=ALLOWED_TOOLS,
        mcp_servers={"brain": brain_mcp_server},
        cwd=str(settings.brain_local_path),
        permission_mode="default",
        can_use_tool=_auto_approve_tool,
        max_turns=settings.max_agent_turns,
        env=auth.env,
    )

    full_response = ""
    last_final_text = ""
    last_ping = ""

    async def _emit(text: str) -> None:
        if on_chunk is None or not text:
            return
        try:
            await on_chunk(text)
        except Exception:
            logger.exception("on_chunk callback failed")

    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_text)
        async for message in client.receive_response():
            if not isinstance(message, AssistantMessage):
                continue

            text_parts = [
                block.text for block in message.content if isinstance(block, TextBlock)
            ]
            tool_uses = [
                block for block in message.content if isinstance(block, ToolUseBlock)
            ]
            chunk = "".join(text_parts).strip()
            if chunk:
                full_response += ("\n\n" if full_response else "") + chunk

            if tool_uses:
                # Intermediate turn: drop the model's chatter, emit a dedup ping
                # in capture mode only.
                if intent == "capture":
                    for tool in tool_uses:
                        ping = _TOOL_PINGS.get(tool.name)
                        if ping and ping != last_ping:
                            await _emit(ping)
                            last_ping = ping
                continue

            # Text-only message = candidate final answer. Keep the latest one.
            if chunk:
                last_final_text = chunk

    full_response = full_response.strip()
    if not full_response:
        full_response = "(l'agent n'a produit aucune réponse textuelle)"
        await _emit(full_response)
    elif last_final_text:
        await _emit(last_final_text)
    else:
        # Agent produced text but always alongside tool calls — surface the
        # accumulated text so the user still sees something.
        await _emit(full_response)

    logger.info("agent response:\n%s", full_response)
    return full_response
