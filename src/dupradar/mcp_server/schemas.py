"""Shared I/O contracts for every dupradar MCP tool.

STEP 0 CONTRACT FILE. These models are the agreed interface between the MCP
server (Track A) and anything that calls it (Track B/C agents, Track D
orchestrator). Treat field names/types here as fixed; extend by adding
optional fields, don't rename or remove without updating every caller.

Privacy rule encoded by these shapes: no model below ever carries a field
that could hold raw source code, except the explicit opt-in snippet tool
(not built today).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LocalSource(BaseModel):
    type: Literal["local"] = "local"
    path: str


class RegisterRepoRequest(BaseModel):
    repo_id: str
    source: LocalSource


class RegisterRepoResult(BaseModel):
    repo_id: str
    file_count: int
    loc_total: int
    language_breakdown: dict[str, int]


class ScanRepoFingerprintsRequest(BaseModel):
    repo_id: str


class FunctionFingerprint(BaseModel):
    function_id: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    token_count: int
    fingerprint_hash: str
    param_count: int


class ScanRepoFingerprintsResult(BaseModel):
    repo_id: str
    functions: list[FunctionFingerprint]


class CompareFingerprintsRequest(BaseModel):
    repo_ids: list[str]
    threshold: float = 1.0


class FingerprintMatch(BaseModel):
    function_a: str
    function_b: str
    repo_a: str
    repo_b: str
    similarity: float
    match_type: Literal["exact", "near"]


class CompareFingerprintsResult(BaseModel):
    matches: list[FingerprintMatch]


class ClusterFunctionInput(BaseModel):
    repo_id: str
    qualified_name: str
    loc: int


class EstimateSavingsRequest(BaseModel):
    functions: list[ClusterFunctionInput]
    similarity: float = Field(ge=0.0, le=1.0)


class EstimateSavingsResult(BaseModel):
    duplicated_loc_total: int
    estimated_hours_saved_per_year: float
    tech_debt_score: float = Field(ge=0.0, le=10.0)
    confidence: Literal["low", "medium", "high"]
