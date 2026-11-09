"""Unit tests for the Code Analysis Agent.

`build_code_analysis_agent_prompt` is pure string assembly, so it is tested
directly without any network/SDK call. The live `run_code_analysis()` path
needs Track A's real MCP server (`dupradar.mcp_server.server`) to be
runnable, so it is gated behind RUN_LIVE_AGENT_TESTS and skipped by
default.
"""

from __future__ import annotations

import os

import pytest

from dupradar.agents.code_analysis_agent import (
    ALLOWED_TOOLS,
    build_code_analysis_agent_prompt,
)
from dupradar.config import mcp_tool

REPOS: list[tuple[str, str]] = [
    ("repo_a_payments", "C:/fake/sample_repos/repo_a_payments"),
    ("repo_b_orders", "C:/fake/sample_repos/repo_b_orders"),
    ("repo_c_inventory", "C:/fake/sample_repos/repo_c_inventory"),
]
RUN_ID = "test-run-001"


def test_allowed_tools_are_exactly_the_three_named_mcp_tools():
    expected = {
        mcp_tool("register_repo"),
        mcp_tool("scan_repo_fingerprints"),
        mcp_tool("compare_fingerprints"),
    }
    assert set(ALLOWED_TOOLS) == expected
    assert len(ALLOWED_TOOLS) == 3
    # and they must already be qualified mcp__dupradar__<tool> names
    for tool in ALLOWED_TOOLS:
        assert tool.startswith("mcp__dupradar__")


def test_build_prompt_returns_nonempty_system_and_user_prompt():
    system_prompt, user_prompt = build_code_analysis_agent_prompt(REPOS, RUN_ID)
    assert isinstance(system_prompt, str) and system_prompt.strip()
    assert isinstance(user_prompt, str) and user_prompt.strip()


def test_system_prompt_names_the_three_tools_and_privacy_rule():
    system_prompt, _ = build_code_analysis_agent_prompt(REPOS, RUN_ID)
    assert "register_repo" in system_prompt
    assert "scan_repo_fingerprints" in system_prompt
    assert "compare_fingerprints" in system_prompt
    # the "never see raw source" privacy guarantee must be explicit
    lowered = system_prompt.lower()
    assert "source" in lowered
    assert "json" in lowered  # output-contract instructions present


def test_user_prompt_lists_every_repo_id_and_path_explicitly():
    _, user_prompt = build_code_analysis_agent_prompt(REPOS, RUN_ID)
    for repo_id, path in REPOS:
        assert repo_id in user_prompt
        assert path in user_prompt


def test_user_prompt_states_the_run_id():
    _, user_prompt = build_code_analysis_agent_prompt(REPOS, RUN_ID)
    assert RUN_ID in user_prompt


def test_user_prompt_shows_the_expected_runreport_json_shape():
    _, user_prompt = build_code_analysis_agent_prompt(REPOS, RUN_ID)
    for key in (
        "run_id",
        "stage",
        "duplication",
        "repos",
        "clusters",
        "cluster_id",
        "similarity",
        "match_type",
        "functions",
        "function_id",
        "qualified_name",
        "file_path",
        "start_line",
        "end_line",
        "loc",
    ):
        assert key in user_prompt, f"expected {key!r} to appear in user prompt"


def test_user_prompt_mentions_each_required_tool_call_step():
    _, user_prompt = build_code_analysis_agent_prompt(REPOS, RUN_ID)
    assert "register_repo(" in user_prompt
    assert "scan_repo_fingerprints(" in user_prompt
    assert "compare_fingerprints(" in user_prompt


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_AGENT_TESTS"),
    reason=(
        "live Code Analysis Agent run requires Track A's MCP server "
        "(dupradar.mcp_server.server) to exist and be runnable; "
        "set RUN_LIVE_AGENT_TESTS=1 to opt in"
    ),
)
def test_run_code_analysis_live_against_sample_repos():
    from dupradar.agents.code_analysis_agent import run_code_analysis
    from dupradar.config import SAMPLE_REPOS_DIR
    from dupradar.schemas.reports import RunReport

    live_repos = [
        ("repo_a_payments", str(SAMPLE_REPOS_DIR / "repo_a_payments")),
        ("repo_b_orders", str(SAMPLE_REPOS_DIR / "repo_b_orders")),
        ("repo_c_inventory", str(SAMPLE_REPOS_DIR / "repo_c_inventory")),
    ]
    report = run_code_analysis(live_repos, "live-test-run")
    assert isinstance(report, RunReport)
    assert report.stage == "duplication"
    assert set(report.repos) == {repo_id for repo_id, _ in live_repos}
