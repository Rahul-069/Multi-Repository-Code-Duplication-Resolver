"""Shared report contracts passed between pipeline stages.

STEP 0 CONTRACT FILE. One `Cluster` model is progressively enriched as it
flows Code Analysis -> Abstraction -> Impact Assessment -> Migration; each
stage only ever fills in its own optional field(s), never raw source. Each
stage dumps the same `RunReport` shape to a different filename:

    duplication -> data/runs/<run_id>/duplication_report.json
    abstraction -> data/runs/<run_id>/abstraction_report.json
    impact      -> data/runs/<run_id>/impact_report.json
    migration   -> data/runs/<run_id>/final_report.json
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Stage = Literal["duplication", "abstraction", "impact", "migration"]


class FunctionRef(BaseModel):
    repo_id: str
    function_id: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    loc: int


class ProposedAbstraction(BaseModel):
    api_name: str
    signature_sketch: str
    rationale: str
    security_notes: str


class ImpactAssessment(BaseModel):
    maintenance_savings_hours_per_year: float
    tech_debt_score: float
    consolidation_risk: Literal["low", "medium", "high"]
    risk_reasons: list[str]
    priority_rank: int


class MigrationStep(BaseModel):
    step_number: int
    action: str
    owning_repo: str
    suggested_pr_description: str
    suggested_tests: list[str]
    rollback_plan: str


class Cluster(BaseModel):
    cluster_id: str
    similarity: float
    match_type: Literal["exact", "near"]
    functions: list[FunctionRef]

    # filled in by the Abstraction Agent
    proposed_abstraction: ProposedAbstraction | None = None
    # filled in by the Impact Assessment Agent
    impact: ImpactAssessment | None = None
    # filled in by the Migration Agent
    migration_plan: list[MigrationStep] | None = None
    suggested_shared_package_path: str | None = None


class RunReport(BaseModel):
    run_id: str
    stage: Stage
    repos: list[str]
    clusters: list[Cluster]
