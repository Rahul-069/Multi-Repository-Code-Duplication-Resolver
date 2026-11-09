"""Unit tests for the Abstraction Agent.

`test_run_abstraction_against_fixture` makes one real (tool-free, cheap)
network call to Claude, per the Track B spec: it's the single live check
proving the schema wiring (fixture JSON -> RunReport -> model ->
RunReport) actually works end to end. It needs no MCP server
(allowed_tools=[]/mcp_servers={}), so unlike the Code Analysis Agent's
live path it is NOT gated behind RUN_LIVE_AGENT_TESTS. There is no
retry/loop here by design.
"""

from __future__ import annotations

from pathlib import Path

from dupradar.agents.abstraction_agent import (
    build_abstraction_agent_prompt,
    run_abstraction,
)
from dupradar.schemas.reports import RunReport

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "duplication_report.json"
)


def _load_fixture_report() -> RunReport:
    return RunReport.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_loads_and_validates_as_duplication_stage():
    report = _load_fixture_report()
    assert report.stage == "duplication"
    assert len(report.clusters) == 1
    assert report.clusters[0].proposed_abstraction is None


def test_build_prompt_embeds_fixture_report_contents():
    report = _load_fixture_report()
    system_prompt, user_prompt = build_abstraction_agent_prompt(report)
    assert isinstance(system_prompt, str) and system_prompt.strip()
    assert "security_notes" in system_prompt  # security-note guidance present
    assert report.run_id in user_prompt
    assert "cluster-0001" in user_prompt
    assert "validate_email" in user_prompt
    assert "is_valid_email" in user_prompt


def test_run_abstraction_against_fixture():
    report = _load_fixture_report()
    assert report.stage == "duplication"

    result = run_abstraction(report)

    assert isinstance(result, RunReport)
    assert result.stage == "abstraction"
    assert result.run_id == report.run_id
    assert result.repos == report.repos
    assert len(result.clusters) == len(report.clusters) == 1

    cluster = result.clusters[0]
    assert cluster.cluster_id == "cluster-0001"
    # untouched fields must survive round-trip unchanged
    assert cluster.impact is None
    assert cluster.migration_plan is None
    assert [f.function_id for f in cluster.functions] == [
        f.function_id for f in report.clusters[0].functions
    ]

    abstraction = cluster.proposed_abstraction
    assert abstraction is not None
    assert abstraction.api_name.strip()
    assert abstraction.signature_sketch.strip()
    assert abstraction.rationale.strip()
    assert abstraction.security_notes.strip()
