"""Code Analysis Agent — pipeline stage 1 of 4.

Given a list of (repo_id, path) pairs, calls `register_repo` then
`scan_repo_fingerprints` for EVERY repo, then `compare_fingerprints` ONCE
across all repo_ids, and emits a `RunReport` with `stage="duplication"`.

Privacy: this agent's `allowed_tools` are restricted to exactly the three
MCP tools below (see `dupradar.agents.runner.build_options` — `tools=[]`
always, so no built-in Bash/Read/Grep/Write ever reaches a repo path). Only
hashes/metadata flow through this agent, never raw source — the MCP server
(Track A) is the only process that ever touches repo file contents.
"""

from __future__ import annotations

import json
from pathlib import Path

from dupradar.agents.runner import extract_json, run_agent
from dupradar.config import mcp_servers_config, mcp_tool
from dupradar.schemas.reports import RunReport

PROMPT_PATH = Path(__file__).parent / "prompts" / "code_analysis.md"

# The only three MCP tools this agent is ever allowed to call.
ALLOWED_TOOLS = [
    mcp_tool("register_repo"),
    mcp_tool("scan_repo_fingerprints"),
    mcp_tool("compare_fingerprints"),
]

# The exact JSON shape the agent must respond with (embedded in the user
# prompt as a literal example so the model has no ambiguity about field
# names/nesting). Values are placeholders, not real output.
_EXAMPLE_OUTPUT_SHAPE = {
    "run_id": "<run_id>",
    "stage": "duplication",
    "repos": ["<repo_id_1>", "<repo_id_2>"],
    "clusters": [
        {
            "cluster_id": "cluster-0001",
            "similarity": 1.0,
            "match_type": "exact",
            "functions": [
                {
                    "repo_id": "<repo_id>",
                    "function_id": "<function_id>",
                    "qualified_name": "<qualified_name>",
                    "file_path": "<file_path>",
                    "start_line": 0,
                    "end_line": 0,
                    "loc": 0,
                }
            ],
            "proposed_abstraction": None,
            "impact": None,
            "migration_plan": None,
            "suggested_shared_package_path": None,
        }
    ],
}


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_code_analysis_agent_prompt(
    repos: list[tuple[str, str]], run_id: str
) -> tuple[str, str]:
    """Build the (system_prompt, user_prompt) pair for a Code Analysis Agent run.

    `repos` is a list of (repo_id, path) pairs. The user prompt explicitly
    lists every repo_id/path, states the run_id, spells out the required
    tool-call sequence (register -> scan for every repo, then ONE
    compare_fingerprints across all of them), and shows the exact JSON
    shape the final response must match.
    """
    system_prompt = _load_system_prompt()

    repo_ids = [repo_id for repo_id, _ in repos]
    repo_lines = "\n".join(
        f"  {i + 1}. repo_id={repo_id!r}, path={path!r}"
        for i, (repo_id, path) in enumerate(repos)
    )
    repo_id_list_literal = ", ".join(repr(repo_id) for repo_id in repo_ids)

    example_shape_json = json.dumps(_EXAMPLE_OUTPUT_SHAPE, indent=2)

    user_prompt = f"""Run id: {run_id}

Repositories to analyze (there are {len(repos)}). You must register AND
scan EVERY one of these before calling compare_fingerprints:
{repo_lines}

Steps:
1. For each repo above, call register_repo(repo_id=<repo_id>, path=<path>).
2. For each repo above, call scan_repo_fingerprints(repo_id=<repo_id>).
3. Only once ALL {len(repos)} repos have been registered and scanned, call
   compare_fingerprints(repo_ids=[{repo_id_list_literal}]) ONCE, across all
   of them together in a single call.
4. Group the matches returned by compare_fingerprints into clusters using
   connected components (union-find) over shared function ids: if a
   function_id appears in more than one match, every function it
   transitively matches belongs to ONE cluster, not separate pairwise
   clusters. A hash shared by 3 repos must become a single 3-member
   cluster. Assign cluster_id values "cluster-0001", "cluster-0002", ...
   in a stable order. A cluster's similarity/match_type come from its
   underlying matches (use 1.0 / "exact" when every match in the cluster
   is an exact match).
5. For each cluster, build its `functions` list using the FunctionFingerprint
   metadata already returned by scan_repo_fingerprints for every function_id
   involved: repo_id, function_id, qualified_name, file_path, start_line,
   end_line, and loc (loc = end_line - start_line + 1). Never use anything
   other than that returned metadata.
6. Only include clusters with 2 or more member functions. If
   compare_fingerprints returns no matches at all, use "clusters": [].

Respond with EXACTLY ONE raw JSON object matching this shape (no markdown
fence, no prose before or after it, run_id/repos/stage filled with the
real values from this run):

{example_shape_json}
"""
    return system_prompt, user_prompt


def run_code_analysis(repos: list[tuple[str, str]], run_id: str) -> RunReport:
    """Run the Code Analysis Agent end-to-end and return a validated RunReport.

    Calls the real Claude Agent SDK (via `dupradar.agents.runner.run_agent`)
    with the MCP server config from `dupradar.config.mcp_servers_config()`
    and `allowed_tools` restricted to register_repo/scan_repo_fingerprints/
    compare_fingerprints — this requires Track A's
    `dupradar.mcp_server.server` to be runnable.
    """
    system_prompt, user_prompt = build_code_analysis_agent_prompt(repos, run_id)

    response_text = run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        allowed_tools=ALLOWED_TOOLS,
        mcp_servers=mcp_servers_config(),
    )

    json_text = extract_json(response_text)
    data = json.loads(json_text)
    return RunReport.model_validate(data)
