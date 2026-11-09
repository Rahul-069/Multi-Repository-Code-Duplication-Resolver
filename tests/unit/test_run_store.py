"""Unit tests for storage/run_store.py -- pure file I/O, no agents, no network.

Every test redirects `run_store.DATA_RUNS_DIR` to a pytest `tmp_path` so
this suite never touches the real `data/runs/` directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dupradar.schemas.reports import RunReport
from dupradar.storage import run_store

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "duplication_report.json"
)


def _load_fixture_report() -> RunReport:
    return RunReport.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _isolated_runs_dir(tmp_path, monkeypatch):
    """Redirect DATA_RUNS_DIR to a throwaway tmp dir for every test here."""
    monkeypatch.setattr(run_store, "DATA_RUNS_DIR", tmp_path)
    return tmp_path


def test_new_run_id_format():
    run_id = run_store.new_run_id()
    assert run_id.startswith("run-")
    assert run_id[len("run-") :].isdigit()


def test_save_stage_report_writes_expected_filename(tmp_path):
    report = _load_fixture_report()
    assert report.stage == "duplication"

    path = run_store.save_stage_report(report)

    assert path == tmp_path / report.run_id / "duplication_report.json"
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == report.run_id
    assert on_disk["stage"] == "duplication"


@pytest.mark.parametrize(
    "stage,filename",
    [
        ("duplication", "duplication_report.json"),
        ("abstraction", "abstraction_report.json"),
        ("impact", "impact_report.json"),
        ("migration", "final_report.json"),
    ],
)
def test_save_stage_report_filename_mapping(tmp_path, stage, filename):
    report = _load_fixture_report().model_copy(update={"stage": stage})

    path = run_store.save_stage_report(report)

    assert path.name == filename
    assert path == tmp_path / report.run_id / filename


def test_load_stage_report_round_trip():
    report = _load_fixture_report()
    run_store.save_stage_report(report)

    loaded = run_store.load_stage_report(report.run_id, "duplication")

    assert loaded == report


def test_load_final_report_round_trip():
    report = _load_fixture_report().model_copy(update={"stage": "migration"})
    run_store.save_stage_report(report)

    loaded = run_store.load_final_report(report.run_id)

    assert loaded == report
    assert loaded.stage == "migration"


def test_load_stage_report_missing_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        run_store.load_stage_report("no-such-run", "duplication")


def test_load_final_report_missing_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        run_store.load_final_report("no-such-run")


def test_save_stage_report_creates_run_dir(tmp_path):
    report = _load_fixture_report()
    assert not (tmp_path / report.run_id).exists()

    run_store.save_stage_report(report)

    assert (tmp_path / report.run_id).is_dir()
