"""Shared constants. Keep this tiny — real per-track settings live in each track's own module."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RUNS_DIR = PROJECT_ROOT / "data" / "runs"
SAMPLE_REPOS_DIR = PROJECT_ROOT / "sample_repos"

DEFAULT_SIMILARITY_THRESHOLD = 1.0  # exact-hash only for today's build

MCP_SERVER_NAME = "dupradar"


def mcp_servers_config() -> dict[str, dict]:
    """The stdio MCP server config block every agent/orchestrator call uses.

    Uses `sys.executable` so the spawned server runs under this same venv.
    """
    return {
        MCP_SERVER_NAME: {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "dupradar.mcp_server.server"],
        }
    }


def mcp_tool(name: str) -> str:
    """Qualify a bare MCP tool name (e.g. "scan_repo_fingerprints") into the
    `mcp__<server>__<tool>` form `allowed_tools` expects."""
    return f"mcp__{MCP_SERVER_NAME}__{name}"
