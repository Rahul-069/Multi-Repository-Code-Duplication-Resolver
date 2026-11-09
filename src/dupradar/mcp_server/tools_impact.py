"""Pure-math implementation of the `estimate_savings` MCP tool.

STEP 0 CONTRACT NOTE: this module deliberately has **no** FastMCP / MCP SDK
dependency and does **no** filesystem or network I/O — it only aggregates
numbers that upstream stages (Code Analysis -> Abstraction) already derived
from fingerprint metadata (repo id, qualified name, LOC). That purity is the
whole reason Track C owns this tool even though the other three MCP tools
(`register_repo`, `scan_repo_fingerprints`, `compare_fingerprints`) live
alongside Track A's `server.py`: `estimate_savings_impl` is fully testable
in isolation, with no server/process needed.

------------------------------------------------------------------------
REGISTRATION SNIPPET — wire this into `mcp_server/server.py`.

`server.py` did not exist yet at the time this file was written (Track A
builds it in parallel), so the real `@mcp.tool()` wrapper lives here as a
comment instead of as a live edit to that file. Once `server.py` exists,
add this (or the moral equivalent) to it:

    from dupradar.mcp_server.tools_impact import estimate_savings_impl

    @mcp.tool()
    def estimate_savings(functions: list[dict], similarity: float) -> dict:
        \"\"\"Estimate duplicated LOC / maintenance savings / tech-debt score
        for one duplicate cluster. `functions` is a list of
        {"repo_id": str, "qualified_name": str, "loc": int} — one entry per
        duplicate copy. Mirrors EstimateSavingsRequest/EstimateSavingsResult
        in mcp_server/schemas.py. No filesystem access.
        \"\"\"
        return estimate_savings_impl(functions, similarity)
------------------------------------------------------------------------
"""

from __future__ import annotations

from dupradar.mcp_server.schemas import EstimateSavingsResult

# --- Heuristic constants -------------------------------------------------
# These are explicitly ASSUMED proxies for a one-day capstone demo, not
# measured maintenance data. Documented here so anyone reviewing the numbers
# knows exactly what they encode and can tune them later.

# Assumed average engineer-hours/year spent on redundant maintenance (bug
# fixes, feature-parity updates, review overhead) per LOC of duplicated code
# left unconsolidated. A placeholder proxy, not derived from telemetry.
HOURS_SAVED_PER_DUPLICATED_LOC_PER_YEAR = 0.5

# tech_debt_score (0-10) heuristic weights: debt grows with HOW MANY copies
# exist (more copies == more places that can silently drift out of sync)
# and with HOW MUCH code is duplicated (bigger copy-pasted blocks cost more
# to carry). Each copy beyond the first contributes a flat amount; each
# duplicated LOC contributes a smaller incremental amount. The combined
# score is clamped into [0, 10] to satisfy EstimateSavingsResult's bounds.
TECH_DEBT_POINTS_PER_EXTRA_COPY = 3.0
TECH_DEBT_POINTS_PER_DUPLICATED_LOC = 0.1
TECH_DEBT_SCORE_MIN = 0.0
TECH_DEBT_SCORE_MAX = 10.0


def estimate_savings_impl(functions: list[dict], similarity: float) -> dict:
    """Aggregate maintenance-savings/tech-debt numbers for one duplicate cluster.

    Pure function: no filesystem, network, or MCP dependency. Operates only
    on metadata the caller already has (this is why it is safe to run
    outside the repo-touching MCP server process).

    Args:
        functions: one dict per duplicate copy in the cluster, each shaped
            like `{"repo_id": str, "qualified_name": str, "loc": int}`
            (mirrors `ClusterFunctionInput` in mcp_server/schemas.py).
        similarity: the cluster's match similarity, in [0.0, 1.0]. `1.0` is
            an exact hash match (the only kind produced today); lower
            values are reserved for future near-duplicate scoring.

    Returns:
        A dict with exactly the fields of `EstimateSavingsResult`:
        `duplicated_loc_total`, `estimated_hours_saved_per_year`,
        `tech_debt_score`, `confidence`.
    """
    copy_count = len(functions)
    loc_values = [int(f["loc"]) for f in functions]
    total_loc = sum(loc_values)
    max_loc = max(loc_values, default=0)

    # LOC eliminated by consolidating N copies down into 1 surviving
    # implementation: everything except the single copy that remains.
    duplicated_loc_total = total_loc - max_loc

    estimated_hours_saved_per_year = (
        duplicated_loc_total * HOURS_SAVED_PER_DUPLICATED_LOC_PER_YEAR
    )

    extra_copies = max(copy_count - 1, 0)
    raw_tech_debt_score = (
        extra_copies * TECH_DEBT_POINTS_PER_EXTRA_COPY
        + duplicated_loc_total * TECH_DEBT_POINTS_PER_DUPLICATED_LOC
    )
    tech_debt_score = max(
        TECH_DEBT_SCORE_MIN, min(TECH_DEBT_SCORE_MAX, raw_tech_debt_score)
    )

    # Confidence reflects how much we trust these numbers as a real
    # duplication signal (not how big the savings are): a clean exact match
    # with at least two independent copies is "high" evidence; two-or-more
    # copies that aren't a clean exact match is "medium"; fewer than two
    # copies (nothing to actually consolidate) is "low" regardless of
    # similarity.
    if similarity == 1.0 and copy_count >= 2:
        confidence = "high"
    elif copy_count >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # Round-trip through the pydantic model so the returned dict is
    # guaranteed to match EstimateSavingsResult's field names/types/bounds
    # exactly (and so an out-of-range score would fail loudly here rather
    # than silently reach a caller).
    result = EstimateSavingsResult(
        duplicated_loc_total=duplicated_loc_total,
        estimated_hours_saved_per_year=estimated_hours_saved_per_year,
        tech_debt_score=tech_debt_score,
        confidence=confidence,
    )
    return result.model_dump()
