"""Migration Agent — pipeline stage 4 of 4 (final stage).

Takes a `RunReport` at `stage="impact"` and, purely from metadata already
present in the report (no MCP tools — there is nothing left to fetch),
produces an ordered `migration_plan` plus a `suggested_shared_package_path`
for every cluster. Returns the same report at `stage="migration"`.
"""

from __future__ import annotations

import json
from pathlib import Path

from dupradar.agents.runner import extract_json, run_agent
from dupradar.schemas.reports import RunReport

_PROMPT_PATH = Path(__file__).parent / "prompts" / "migration.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_prompt(report: RunReport) -> str:
    report_json = report.model_dump_json(indent=2)
    return (
        'Here is the input RunReport ("stage": "impact"). Follow your '
        "instructions: process clusters in priority_rank order, produce a "
        "migration_plan and suggested_shared_package_path for every "
        "cluster, and return the complete updated RunReport as a single "
        'raw JSON object with "stage": "migration".\n\n'
        f"{report_json}"
    )


def run_migration(report: RunReport) -> RunReport:
    """Run the Migration Agent on a stage="impact" RunReport.

    Returns the same report at stage="migration" with every cluster's
    `migration_plan` and `suggested_shared_package_path` populated. Raises
    `ValueError` if the model's output doesn't validate as a `RunReport` or
    doesn't come back at the expected stage.

    No MCP tools are used in this stage (`allowed_tools=[]`), so no MCP
    server process is spawned.
    """
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(report)

    raw_text = run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        allowed_tools=[],
    )

    json_text = extract_json(raw_text)
    data = json.loads(json_text)
    updated = RunReport.model_validate(data)

    if updated.stage != "migration":
        raise ValueError(
            f"Migration Agent returned stage={updated.stage!r}, expected "
            f"'migration'. Raw model output:\n{raw_text}"
        )

    return updated
