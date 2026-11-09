"""Deterministic pipeline orchestrator chaining all 4 agent stages.

`run_pipeline` runs four separate, sequential agent calls in a fixed order
-- Code Analysis -> Abstraction -> Impact Assessment -> Migration -- saving
each stage's RunReport to disk before moving to the next. The fixed order
is enforced here in plain code (not left to model-driven delegation),
which is what makes the "only the Code Analysis Agent reaches
repo-touching MCP tools" privacy guarantee real rather than a prompt-level
suggestion.

`run_pipeline_stubbed` has the exact same shape but is wired to 4 trivial
inline stub functions instead of the real agents -- zero network calls,
zero dependency on teammates' modules -- so storage/CLI/dashboard plumbing
can be built and tested without ever blocking on Track A/B/C's progress.

The four imports below are the fixed contract for Track B/C's agents
(see each module for its exact signature). They are normal top-level
imports, on purpose: if a teammate's module is still missing or broken
mid-build, importing this module should fail immediately and visibly
(and `run_pipeline_stubbed`'s own tests are what you run in the meantime)
rather than silently deferring the failure to call-time or papering over
it with a fallback implementation.
"""

from __future__ import annotations

from dupradar.agents.abstraction_agent import run_abstraction
from dupradar.agents.code_analysis_agent import run_code_analysis
from dupradar.agents.impact_assessment_agent import run_impact_assessment
from dupradar.agents.migration_agent import run_migration
from dupradar.schemas.reports import (
    Cluster,
    FunctionRef,
    ImpactAssessment,
    MigrationStep,
    ProposedAbstraction,
    RunReport,
)
from dupradar.storage.run_store import new_run_id, save_stage_report


def run_pipeline(repos: list[tuple[str, str]], run_id: str | None = None) -> RunReport:
    """Run the real 4-stage pipeline end to end, saving each stage's report.

    `repos` is a list of (repo_id, path) pairs. Requires Track A's MCP
    server to be runnable and Track B/C's agent modules to be importable.
    See `run_pipeline_stubbed` for a network-free stand-in used to test
    orchestration/storage/CLI/dashboard plumbing in isolation.
    """
    run_id = run_id or new_run_id()

    report = run_code_analysis(repos, run_id)
    save_stage_report(report)

    report = run_abstraction(report)
    save_stage_report(report)

    report = run_impact_assessment(report)
    save_stage_report(report)

    report = run_migration(report)
    save_stage_report(report)  # stage == "migration" -> lands as final_report.json

    return report


def _stub_code_analysis(repos: list[tuple[str, str]], run_id: str) -> RunReport:
    """Trivial inline stand-in for the real Code Analysis Agent.

    Fabricates one 2-member cluster across the first two repos (if at
    least 2 are given) so downstream stub stages have something to
    enrich. Zero network/MCP calls.
    """
    repo_ids = [repo_id for repo_id, _ in repos]
    clusters: list[Cluster] = []
    if len(repo_ids) >= 2:
        clusters.append(
            Cluster(
                cluster_id="cluster-0001",
                similarity=1.0,
                match_type="exact",
                functions=[
                    FunctionRef(
                        repo_id=repo_ids[0],
                        function_id=f"{repo_ids[0]}:stub_function",
                        qualified_name="stub_function",
                        file_path="stub.py",
                        start_line=1,
                        end_line=5,
                        loc=5,
                    ),
                    FunctionRef(
                        repo_id=repo_ids[1],
                        function_id=f"{repo_ids[1]}:stub_function_dupe",
                        qualified_name="stub_function_dupe",
                        file_path="stub.py",
                        start_line=1,
                        end_line=5,
                        loc=5,
                    ),
                ],
            )
        )
    return RunReport(run_id=run_id, stage="duplication", repos=repo_ids, clusters=clusters)


def _stub_abstraction(report: RunReport) -> RunReport:
    """Trivial inline stand-in for the real Abstraction Agent."""
    clusters = [
        cluster.model_copy(
            update={
                "proposed_abstraction": ProposedAbstraction(
                    api_name="stub_shared_function",
                    signature_sketch="def stub_shared_function(*args, **kwargs)",
                    rationale="Stubbed rationale for orchestration/storage testing.",
                    security_notes="Stubbed security notes; no real analysis performed.",
                )
            }
        )
        for cluster in report.clusters
    ]
    return report.model_copy(update={"stage": "abstraction", "clusters": clusters})


def _stub_impact_assessment(report: RunReport) -> RunReport:
    """Trivial inline stand-in for the real Impact Assessment Agent."""
    clusters = [
        cluster.model_copy(
            update={
                "impact": ImpactAssessment(
                    maintenance_savings_hours_per_year=10.0,
                    tech_debt_score=5.0,
                    consolidation_risk="low",
                    risk_reasons=["Stubbed risk reason for orchestration/storage testing."],
                    priority_rank=rank,
                )
            }
        )
        for rank, cluster in enumerate(report.clusters, start=1)
    ]
    return report.model_copy(update={"stage": "impact", "clusters": clusters})


def _stub_migration(report: RunReport) -> RunReport:
    """Trivial inline stand-in for the real Migration Agent."""
    clusters = [
        cluster.model_copy(
            update={
                "migration_plan": [
                    MigrationStep(
                        step_number=1,
                        action="Stubbed migration step for orchestration/storage testing.",
                        owning_repo=cluster.functions[0].repo_id,
                        suggested_pr_description="Stub PR description.",
                        suggested_tests=["test_stub_shared_function"],
                        rollback_plan="Revert the stub PR.",
                    )
                ],
                "suggested_shared_package_path": "shared/stub_shared_function.py",
            }
        )
        for cluster in report.clusters
    ]
    return report.model_copy(update={"stage": "migration", "clusters": clusters})


def run_pipeline_stubbed(repos: list[tuple[str, str]], run_id: str | None = None) -> RunReport:
    """Same shape as `run_pipeline`, but wired to trivial inline stub stages.

    Zero network calls, zero dependency on teammates' agent modules. This
    is what orchestration/storage/CLI/dashboard plumbing is built and
    tested against.
    """
    run_id = run_id or new_run_id()

    report = _stub_code_analysis(repos, run_id)
    save_stage_report(report)

    report = _stub_abstraction(report)
    save_stage_report(report)

    report = _stub_impact_assessment(report)
    save_stage_report(report)

    report = _stub_migration(report)
    save_stage_report(report)

    return report
