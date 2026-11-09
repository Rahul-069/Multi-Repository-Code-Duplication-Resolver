"""Impact Assessment Agent — pipeline stage 3 of 4.

Takes a `RunReport` at `stage="abstraction"`, calls the `estimate_savings`
MCP tool once per cluster (real tool call — this agent never computes those
numbers itself), has the model layer risk reasoning and a priority rank on
top of the tool's numeric output, and returns the same report at
`stage="impact"` with every cluster's `impact` field populated.
"""

from __future__ import annotations

import json
from pathlib import Path

from dupradar.agents.runner import extract_json, run_agent
from dupradar.config import mcp_servers_config, mcp_tool
from dupradar.schemas.reports import RunReport

_PROMPT_PATH = Path(__file__).parent / "prompts" / "impact_assessment.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_prompt(report: RunReport) -> str:
    report_json = report.model_dump_json(indent=2)
    return (
        'Here is the input RunReport ("stage": "abstraction"). Follow your '
        "instructions: call the estimate_savings tool once per cluster, add "
        "risk reasoning and a priority_rank on top of its output, and return "
        'the complete updated RunReport as a single raw JSON object with '
        '"stage": "impact".\n\n'
        f"{report_json}"
    )


def run_impact_assessment(report: RunReport) -> RunReport:
    """Run the Impact Assessment Agent on a stage="abstraction" RunReport.

    Returns the same report at stage="impact" with every cluster's `impact`
    field populated. Raises `ValueError` if the model's output doesn't
    validate as a `RunReport` or doesn't come back at the expected stage.
    """
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(report)

    raw_text = run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        allowed_tools=[mcp_tool("estimate_savings")],
        mcp_servers=mcp_servers_config(),
    )

    json_text = extract_json(raw_text)
    data = json.loads(json_text)
    updated = RunReport.model_validate(data)

    if updated.stage != "impact":
        raise ValueError(
            f"Impact Assessment Agent returned stage={updated.stage!r}, "
            f"expected 'impact'. Raw model output:\n{raw_text}"
        )

    return updated
