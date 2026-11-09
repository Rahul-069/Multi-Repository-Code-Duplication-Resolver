"""Standalone dupradar MCP server -- stdio transport.

The only process that ever touches raw repo file contents. Agents/the
orchestrator get `allowed_tools=["mcp__dupradar__scan_repo_fingerprints",
...]` only, never generic file-read access to repo paths (see
`dupradar.config.mcp_tool`). Launched as:

    python -m dupradar.mcp_server.server

(see `dupradar.config.mcp_servers_config()`, which spawns exactly this
module, under `sys.executable`, over stdio).

DEVIATION FROM THE LITERAL SPEC TEXT ("from mcp.server.fastmcp import
FastMCP"): the `mcp` package actually installed in this project's venv is
v2.x (2.3.0), where `FastMCP` was renamed to `MCPServer` -- importing
`mcp.server.fastmcp` in this venv raises `ModuleNotFoundError` with a
message pointing at `mcp.server.mcpserver.MCPServer` as the replacement.
That class is aliased back to the name `FastMCP` below so everything else
reads exactly like the spec (`mcp = FastMCP("dupradar")`, `@mcp.tool()`,
`mcp.run()`), and its constructor/`.tool()`/`.run()` signatures are
drop-in compatible for the way this module uses them (verified directly
against the installed package).

Extension point for Person C's `estimate_savings` (`tools_impact.py`,
not owned by this track): that module should `from
dupradar.mcp_server.server import mcp` and add its own `@mcp.tool()`
function the same way the three tools below do. It is intentionally not
imported from here, since `tools_impact.py` does not exist yet in this
track's checkout and this module must stay importable on its own.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer as FastMCP

from dupradar.mcp_server.tools_compare import compare_fingerprints as _compare_fingerprints
from dupradar.mcp_server.tools_impact import estimate_savings_impl as _estimate_savings_impl
from dupradar.mcp_server.tools_repo import register_repo as _register_repo
from dupradar.mcp_server.tools_repo import scan_repo_fingerprints as _scan_repo_fingerprints

mcp = FastMCP("dupradar")


@mcp.tool()
def register_repo(repo_id: str, path: str) -> dict:
    """Register a local repo root for scanning.

    Validates that `path` is an existing directory, walks its `.py` files
    to compute file_count/loc_total/language_breakdown, and caches the
    root under `repo_id` for later `scan_repo_fingerprints` calls.
    """
    return _register_repo(repo_id, path)


@mcp.tool()
def scan_repo_fingerprints(repo_id: str) -> dict:
    """Walk a registered repo's `.py` files and return normalized, hashed
    function fingerprints for every function/method found -- metadata
    only (hashes, names, line ranges, counts); never source text.
    """
    return _scan_repo_fingerprints(repo_id)


@mcp.tool()
def compare_fingerprints(repo_ids: list[str], threshold: float = 1.0) -> dict:
    """Find cross-repo function pairs sharing an identical fingerprint
    hash among already-scanned repos. `threshold` is accepted but unused
    today -- matching is exact-hash only (no winnowing yet).
    """
    return _compare_fingerprints(repo_ids, threshold)


@mcp.tool()
def estimate_savings(functions: list[dict], similarity: float) -> dict:
    """Estimate duplicated LOC / maintenance savings / tech-debt score for
    one duplicate cluster. `functions` is a list of {"repo_id": str,
    "qualified_name": str, "loc": int}, one entry per duplicate copy.
    Pure aggregation over metadata already produced upstream -- no
    filesystem access.
    """
    return _estimate_savings_impl(functions, similarity)


if __name__ == "__main__":
    mcp.run()
