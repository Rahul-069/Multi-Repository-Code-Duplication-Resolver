"""Abstraction Agent — pipeline stage 2 of 4.

Given a `RunReport` with `stage="duplication"`, proposes a generalized
shared abstraction for every cluster using ONLY the structural metadata
already present on each cluster's `FunctionRef`s (qualified_name,
file_path, loc, ...) — never raw source, which this agent never has access
to in the first place. Returns the SAME `RunReport`, with `stage`
advanced to `"abstraction"` and every cluster's `proposed_abstraction`
filled in.

No MCP tools: `allowed_tools=[]`, `mcp_servers={}`. This agent only reasons
over the JSON passed directly in the user prompt, so (unlike the Code
Analysis Agent) it needs no live MCP server and can be built/tested fully
against a hand-written fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from dupradar.agents.runner import extract_json, run_agent
from dupradar.schemas.reports import RunReport

PROMPT_PATH = Path(__file__).parent / "prompts" / "abstraction.md"


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_abstraction_agent_prompt(report: RunReport) -> tuple[str, str]:
    """Build the (system_prompt, user_prompt) pair for an Abstraction Agent run.

    The user prompt serializes `report` to JSON verbatim and instructs the
    model to return the identical JSON with `stage` advanced and every
    cluster's `proposed_abstraction` filled in, nothing else changed.
    """
    system_prompt = _load_system_prompt()

    report_json = report.model_dump_json(indent=2)

    user_prompt = f"""Here is the duplication report to propose abstractions
for. It is a complete RunReport JSON object with "stage": "duplication":

{report_json}

Return the identical JSON object back, except:
- "stage" changed from "duplication" to "abstraction"
- every cluster's "proposed_abstraction" filled in (api_name,
  signature_sketch, rationale, security_notes — all non-empty strings),
  reasoning only from the structural metadata already in each cluster's
  functions (qualified_name, file_path, start_line, end_line, loc). Never
  assume or invent source code.

Do not change run_id, repos, any cluster's cluster_id/similarity/
match_type/functions, or the other still-null fields (impact,
migration_plan, suggested_shared_package_path) — leave those exactly as
given.

Respond with EXACTLY ONE raw JSON object matching the RunReport schema (no
markdown fence, no prose before or after it).
"""
    return system_prompt, user_prompt


def run_abstraction(report: RunReport) -> RunReport:
    """Run the Abstraction Agent end-to-end and return a validated RunReport.

    Takes a RunReport(stage="duplication"), makes one tool-free Claude call,
    and returns the parsed+validated RunReport(stage="abstraction") with
    every cluster's proposed_abstraction populated.
    """
    system_prompt, user_prompt = build_abstraction_agent_prompt(report)

    response_text = run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        allowed_tools=[],
        mcp_servers={},
    )

    json_text = extract_json(response_text)
    data = json.loads(json_text)
    return RunReport.model_validate(data)
