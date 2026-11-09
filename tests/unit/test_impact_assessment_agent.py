"""Live test for the Impact Assessment Agent (stage 3).

Loads the hand-written `tests/fixtures/abstraction_report.json` fixture
(matching what the Abstraction Agent, built by Track B, outputs) and runs
the REAL `run_impact_assessment()` against it -- a real LLM call that also
makes a real MCP tool call to `estimate_savings` through the dupradar MCP
server. No mocking, no retry loop: if it fails, it fails.
"""

from __future__ import annotations

import json
from pathlib import Path

from dupradar.agents.impact_assessment_agent import run_impact_assessment
from dupradar.schemas.reports import RunReport

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "abstraction_report.json"
)


def _load_fixture_report() -> RunReport:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return RunReport.model_validate(data)


def test_run_impact_assessment_against_fixture():
    report = _load_fixture_report()
    assert report.stage == "abstraction"

    result = run_impact_assessment(report)

    # Real RunReport, correct stage.
    assert isinstance(result, RunReport)
    assert result.stage == "impact"
    assert len(result.clusters) == len(report.clusters)

    seen_ranks = []
    for cluster in result.clusters:
        assert cluster.impact is not None
        assert cluster.impact.priority_rank >= 1
        assert cluster.impact.consolidation_risk in {"low", "medium", "high"}
        assert 0.0 <= cluster.impact.tech_debt_score <= 10.0
        assert cluster.impact.maintenance_savings_hours_per_year >= 0
        assert isinstance(cluster.impact.risk_reasons, list)
        assert len(cluster.impact.risk_reasons) > 0
        seen_ranks.append(cluster.impact.priority_rank)

        # untouched by this stage.
        assert cluster.migration_plan is None
        assert cluster.suggested_shared_package_path is None
        assert cluster.proposed_abstraction == next(
            c.proposed_abstraction
            for c in report.clusters
            if c.cluster_id == cluster.cluster_id
        )

    # dense 1..N ranking across the whole report, no gaps/duplicates.
    assert sorted(seen_ranks) == list(range(1, len(result.clusters) + 1))
