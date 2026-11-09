"""Live test for the Migration Agent (stage 4).

Hand-builds a minimal RunReport at stage="impact" (reusing the fixture
cluster's functions + proposed_abstraction, with a made-up ImpactAssessment
block bolted on) rather than waiting on the Impact Assessment Agent. This is
a real LLM call -- no mocking -- but `run_migration` uses no MCP tools
(`allowed_tools=[]`), so it never touches the MCP server process either way.
"""

from __future__ import annotations

import json
from pathlib import Path

from dupradar.agents.migration_agent import run_migration
from dupradar.schemas.reports import ImpactAssessment, RunReport

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "abstraction_report.json"
)


def _build_impact_stage_report() -> RunReport:
    fixture_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture_report = RunReport.model_validate(fixture_data)
    fixture_cluster = fixture_report.clusters[0]
    assert fixture_cluster.proposed_abstraction is not None  # sanity: fixture is pre-filled

    impact_cluster = fixture_cluster.model_copy(
        update={
            "impact": ImpactAssessment(
                maintenance_savings_hours_per_year=12.0,
                tech_debt_score=4.5,
                consolidation_risk="low",
                risk_reasons=[
                    "Exact hash match (similarity=1.0) between "
                    "repo_a_payments and repo_b_orders.",
                    "Both functions are simple email-shape validators used "
                    "by sibling e-commerce services.",
                ],
                priority_rank=1,
            )
        }
    )

    return RunReport(
        run_id=fixture_report.run_id,
        stage="impact",
        repos=fixture_report.repos,
        clusters=[impact_cluster],
    )


def test_run_migration_against_hand_built_impact_report():
    report = _build_impact_stage_report()
    assert report.stage == "impact"

    result = run_migration(report)

    # Real RunReport, correct stage.
    assert isinstance(result, RunReport)
    assert result.stage == "migration"
    assert len(result.clusters) == 1

    cluster = result.clusters[0]
    valid_repo_ids = {f.repo_id for f in cluster.functions}

    assert cluster.suggested_shared_package_path
    assert isinstance(cluster.suggested_shared_package_path, str)

    assert isinstance(cluster.migration_plan, list)
    assert len(cluster.migration_plan) > 0

    seen_step_numbers = []
    owning_repos = set()
    for step in cluster.migration_plan:
        assert step.step_number >= 1
        assert step.action
        assert step.owning_repo in valid_repo_ids
        assert step.suggested_pr_description
        assert isinstance(step.suggested_tests, list)
        assert len(step.suggested_tests) > 0
        assert step.rollback_plan
        seen_step_numbers.append(step.step_number)
        owning_repos.add(step.owning_repo)

    # step numbers are a dense 1..N sequence (strictly sequential plan).
    assert seen_step_numbers == list(range(1, len(cluster.migration_plan) + 1))
    # owning_repo is consistent across every step of the plan.
    assert len(owning_repos) == 1

    # untouched fields carried through verbatim from the input.
    assert cluster.cluster_id == report.clusters[0].cluster_id
    assert cluster.impact == report.clusters[0].impact
    assert cluster.proposed_abstraction == report.clusters[0].proposed_abstraction
