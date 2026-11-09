"""Unit tests for orchestrator.py.

`run_pipeline_stubbed` is network-free and doesn't import any teammate's
agent module (it fabricates its own stage data inline via the 4 `_stub_*`
helpers), so this test exercises the full save/advance-stage orchestration
loop without needing Track A's MCP server or Track B/C's real agents.

The REAL `run_pipeline()` is deliberately NOT tested here: it needs a live
MCP server plus live Claude calls, which is final-integration territory.
The one test that touches it is gated behind RUN_LIVE_AGENT_TESTS and
skipped by default.

Note: importing `dupradar.orchestrator` at all pulls in its top-level
imports of the 4 real agent functions (see orchestrator.py's docstring for
why those are deliberately not lazy). If a teammate's module doesn't exist
yet, THIS WHOLE FILE will fail to collect with a clear ModuleNotFoundError
-- that is expected mid-build, not a bug in these tests.
"""

from __future__ import annotations

import os

import pytest

from dupradar.orchestrator import run_pipeline, run_pipeline_stubbed
from dupradar.schemas.reports import RunReport
from dupradar.storage import run_store

SAMPLE_REPOS = [
    ("repo_a_payments", "C:/fake/repo_a_payments"),
    ("repo_b_orders", "C:/fake/repo_b_orders"),
    ("repo_c_inventory", "C:/fake/repo_c_inventory"),
]

STAGE_FILENAMES = [
    "duplication_report.json",
    "abstraction_report.json",
    "impact_report.json",
    "final_report.json",
]


@pytest.fixture(autouse=True)
def _isolated_runs_dir(tmp_path, monkeypatch):
    """Redirect DATA_RUNS_DIR to a throwaway tmp dir for every test here."""
    monkeypatch.setattr(run_store, "DATA_RUNS_DIR", tmp_path)
    return tmp_path


def test_run_pipeline_stubbed_returns_final_migration_report():
    report = run_pipeline_stubbed(SAMPLE_REPOS, run_id="test-run-stubbed")

    assert isinstance(report, RunReport)
    assert report.stage == "migration"
    assert report.run_id == "test-run-stubbed"
    assert report.repos == [repo_id for repo_id, _ in SAMPLE_REPOS]


def test_run_pipeline_stubbed_writes_all_four_stage_files(tmp_path):
    report = run_pipeline_stubbed(SAMPLE_REPOS, run_id="test-run-files")

    run_dir = tmp_path / report.run_id
    for filename in STAGE_FILENAMES:
        path = run_dir / filename
        assert path.exists(), f"expected {path} to exist"


def test_run_pipeline_stubbed_generates_run_id_when_omitted():
    report = run_pipeline_stubbed(SAMPLE_REPOS)

    assert report.run_id
    loaded = run_store.load_final_report(report.run_id)
    assert loaded.run_id == report.run_id


def test_run_pipeline_stubbed_clusters_have_expected_shape():
    report = run_pipeline_stubbed(SAMPLE_REPOS, run_id="test-run-shape")

    assert len(report.clusters) >= 1
    cluster = report.clusters[0]
    assert cluster.proposed_abstraction is not None
    assert cluster.impact is not None
    assert cluster.migration_plan is not None
    assert len(cluster.migration_plan) >= 1


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_AGENT_TESTS"),
    reason="Live agent/MCP integration test; set RUN_LIVE_AGENT_TESTS=1 to run.",
)
def test_run_pipeline_live_against_real_agents():
    """Full live integration: real agents + Track A's MCP server.

    Not run by default -- needs all 4 teammates' real modules plus a live
    MCP server process and network access to Claude. Final-integration
    territory, not this track's responsibility.
    """
    report = run_pipeline(SAMPLE_REPOS)
    assert report.stage == "migration"
