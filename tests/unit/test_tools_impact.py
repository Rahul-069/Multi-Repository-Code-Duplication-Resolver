"""Pure unit tests for `estimate_savings_impl` — no agent, no network, no MCP."""

from __future__ import annotations

from dupradar.mcp_server.schemas import EstimateSavingsResult
from dupradar.mcp_server.tools_impact import estimate_savings_impl


def _func(repo_id: str, qualified_name: str, loc: int) -> dict:
    return {"repo_id": repo_id, "qualified_name": qualified_name, "loc": loc}


def test_two_functions_produce_sane_positive_numbers():
    functions = [
        _func("repo_a_payments", "validate_email", 20),
        _func("repo_b_orders", "is_valid_email", 20),
    ]

    result = estimate_savings_impl(functions, similarity=1.0)

    assert result["duplicated_loc_total"] == 20  # (20 + 20) - max(20) = 20
    assert result["estimated_hours_saved_per_year"] == 10.0  # 20 * 0.5
    assert result["estimated_hours_saved_per_year"] > 0
    assert result["tech_debt_score"] > 0
    assert result["confidence"] == "high"


def test_duplicated_loc_total_is_sum_minus_max_for_three_copies():
    functions = [
        _func("repo_a", "f", 30),
        _func("repo_b", "f", 10),
        _func("repo_c", "f", 15),
    ]

    result = estimate_savings_impl(functions, similarity=1.0)

    assert result["duplicated_loc_total"] == 25  # (30 + 10 + 15) - 30


def test_result_validates_against_estimate_savings_result_schema():
    functions = [_func("repo_a", "f", 20), _func("repo_b", "f", 20)]

    result = estimate_savings_impl(functions, similarity=1.0)

    # Round-trips cleanly through the shared contract schema.
    EstimateSavingsResult.model_validate(result)


# --- confidence branches ---------------------------------------------------


def test_confidence_high_requires_exact_similarity_and_two_or_more_copies():
    functions = [_func("repo_a", "f", 10), _func("repo_b", "f", 10)]

    result = estimate_savings_impl(functions, similarity=1.0)

    assert result["confidence"] == "high"


def test_confidence_medium_when_two_or_more_copies_but_not_exact_similarity():
    functions = [_func("repo_a", "f", 10), _func("repo_b", "f", 10)]

    result = estimate_savings_impl(functions, similarity=0.85)

    assert result["confidence"] == "medium"


def test_confidence_low_when_fewer_than_two_copies_even_with_exact_similarity():
    functions = [_func("repo_a", "f", 10)]

    result = estimate_savings_impl(functions, similarity=1.0)

    assert result["confidence"] == "low"


def test_confidence_low_for_empty_functions_list():
    result = estimate_savings_impl([], similarity=1.0)

    assert result["confidence"] == "low"
    assert result["duplicated_loc_total"] == 0
    assert result["estimated_hours_saved_per_year"] == 0.0
    assert result["tech_debt_score"] == 0.0


# --- tech_debt_score clamping ----------------------------------------------


def test_tech_debt_score_clamps_at_upper_bound_for_a_large_cluster():
    # 10 copies * 500 LOC each is way beyond what the raw formula would cap
    # at 10 on its own -- this must clamp, not overflow past 10.
    functions = [_func(f"repo_{i}", "f", 500) for i in range(10)]

    result = estimate_savings_impl(functions, similarity=1.0)

    assert result["tech_debt_score"] == 10.0


def test_tech_debt_score_always_within_bounds_across_many_shapes():
    for copy_count in (0, 1, 2, 5, 50):
        for loc in (0, 1, 10, 1000):
            functions = [_func(f"repo_{i}", "f", loc) for i in range(copy_count)]
            result = estimate_savings_impl(functions, similarity=1.0)
            assert 0.0 <= result["tech_debt_score"] <= 10.0
            assert result["duplicated_loc_total"] >= 0
            assert result["estimated_hours_saved_per_year"] >= 0.0


def test_tech_debt_score_floor_is_zero_for_a_single_tiny_function():
    functions = [_func("repo_a", "f", 1)]

    result = estimate_savings_impl(functions, similarity=1.0)

    assert result["tech_debt_score"] == 0.0  # 0 extra copies, 0 duplicated LOC
