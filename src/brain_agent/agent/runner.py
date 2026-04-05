"""Agent runner: wires the Claude Agent SDK to the brain and executes a single turn."""

from __future__ import annotations

import logging

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
)

from brain_agent.agent.intent import detect_intent
from brain_agent.agent.prompt import build_system_prompt
from brain_agent.brain import repo
from brain_agent.config import get_settings
from brain_agent.tools.brain_mcp import brain_mcp_server

logger = logging.getLogger(__name__)

BUILTIN_TOOLS = ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
MCP_TOOLS = [
    "mcp__brain__validate_brain",
    "mcp__brain__git_commit_push",
]


async def run_turn(user_text: str) -> str:
    """Execute one exchange with the agent and return the final assistant text."""
    settings = get_settings()
    intent = detect_intent(user_text)
    logger.info("intent=%s text=%r", intent, user_text[:100])

    # In capture mode, always pull first so the agent works from a fresh state.
    if intent == "capture":
        async with repo.repo_lock:
            res = await repo.pull_rebase()
            if not res.ok:
                logger.warning("pre-turn pull failed: %s", res.stderr)

    system_prompt = build_system_prompt(intent, settings.brain_local_path)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=settings.anthropic_model,
        allowed_tools=BUILTIN_TOOLS + MCP_TOOLS,
        mcp_servers={"brain": brain_mcp_server},
        cwd=str(settings.brain_local_path),
        permission_mode="acceptEdits",
        max_turns=settings.max_agent_turns,
    )

    response_text = ""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_text)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text

    response_text = response_text.strip()
    if not response_text:
        response_text = "(l'agent n'a produit aucune réponse textuelle)"
    return response_text
