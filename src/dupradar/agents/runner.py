"""Shared one-shot Claude Agent SDK runner used by all 4 agents.

STEP 0 SHARED INFRASTRUCTURE — written once so every agent calls the SDK the
same way. Each agent module should call `run_agent()` (or `run_agent_async`
from async code) rather than touching `claude_agent_sdk` directly.

Privacy/scoping note: pass `tools=[]` always (the caller does this via
`build_options`) so the agent has ZERO access to built-in Bash/Read/Write/
Grep/etc. — the only tools it can ever call are the explicit MCP tools named
in `allowed_tools`. This is what makes the "only the Code Analysis Agent can
reach repo-touching MCP tools" guarantee real rather than a prompt-level
suggestion.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)


class AgentRunError(RuntimeError):
    """Raised when a one-shot agent run errors out or produces no text."""


def build_options(
    *,
    system_prompt: str,
    allowed_tools: list[str],
    mcp_servers: Mapping[str, object] | None = None,
    max_turns: int = 20,
) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        tools=[],  # no built-in Bash/Read/Write/Grep/etc. — MCP tools only
        allowed_tools=allowed_tools,
        mcp_servers=dict(mcp_servers or {}),
        permission_mode="bypassPermissions",
        max_turns=max_turns,
    )


async def run_agent_async(
    *,
    system_prompt: str,
    user_prompt: str,
    allowed_tools: list[str],
    mcp_servers: Mapping[str, object] | None = None,
    max_turns: int = 20,
) -> str:
    """Run one one-shot query and return the last assistant message's text.

    Raises AgentRunError if the run errors or never produces assistant text.
    """
    options = build_options(
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        mcp_servers=mcp_servers,
        max_turns=max_turns,
    )

    last_text_chunks: list[str] = []
    result: ResultMessage | None = None

    async for message in query(prompt=user_prompt, options=options):
        if isinstance(message, AssistantMessage):
            chunks = [block.text for block in message.content if isinstance(block, TextBlock)]
            if chunks:
                last_text_chunks = chunks
        elif isinstance(message, ResultMessage):
            result = message

    if result is not None and result.is_error:
        raise AgentRunError(f"Agent run failed (subtype={result.subtype!r})")
    if not last_text_chunks:
        raise AgentRunError("Agent run produced no assistant text")

    return "\n".join(last_text_chunks).strip()


def run_agent(
    *,
    system_prompt: str,
    user_prompt: str,
    allowed_tools: list[str],
    mcp_servers: Mapping[str, object] | None = None,
    max_turns: int = 20,
) -> str:
    """Sync wrapper around run_agent_async, for CLI/script callers."""
    return asyncio.run(
        run_agent_async(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
            max_turns=max_turns,
        )
    )


def extract_json(text: str) -> str:
    """Pull a JSON object out of model output that may be wrapped in a
    ```json ... ``` fence or have leading/trailing prose. Agents are
    instructed to return pure JSON, but this is a cheap safety net."""
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AgentRunError("No JSON object found in agent output")
    return stripped[start : end + 1]
