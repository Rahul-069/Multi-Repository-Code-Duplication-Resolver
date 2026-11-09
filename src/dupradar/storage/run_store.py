"""Plain JSON file persistence for pipeline stage reports, no DB.

Each run's stage reports live under `DATA_RUNS_DIR / run_id / <filename>`,
one file per stage, written verbatim via `RunReport.model_dump_json`. The
`stage` field on the report itself (not the caller) decides the filename,
so writing a report always lands at the file its own `stage` implies.
"""

from __future__ import annotations

import time
from pathlib import Path

from dupradar.config import DATA_RUNS_DIR
from dupradar.schemas.reports import RunReport

# stage -> filename on disk. "migration" is the pipeline's last stage, so
# its report lands as final_report.json -- what the CLI/dashboard treat as
# the run's result.
STAGE_FILENAMES: dict[str, str] = {
    "duplication": "duplication_report.json",
    "abstraction": "abstraction_report.json",
    "impact": "impact_report.json",
    "migration": "final_report.json",
}


def new_run_id() -> str:
    """Generate a fresh run id, e.g. "run-1733500000"."""
    return f"run-{int(time.time())}"


def _run_dir(run_id: str) -> Path:
    return DATA_RUNS_DIR / run_id


def _stage_filename(stage: str) -> str:
    try:
        return STAGE_FILENAMES[stage]
    except KeyError as exc:
        raise ValueError(
            f"Unknown stage {stage!r}; expected one of {sorted(STAGE_FILENAMES)}"
        ) from exc


def save_stage_report(report: RunReport) -> Path:
    """Write `report` to its stage's JSON file under the run's directory.

    Creates `DATA_RUNS_DIR / report.run_id /` if it doesn't exist yet.
    Returns the path written to.
    """
    run_dir = _run_dir(report.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / _stage_filename(report.stage)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_stage_report(run_id: str, stage: str) -> RunReport:
    """Load and validate the JSON report for `stage` of `run_id`.

    Raises FileNotFoundError if that run/stage has no saved report.
    """
    path = _run_dir(run_id) / _stage_filename(stage)
    if not path.exists():
        raise FileNotFoundError(
            f"No {stage!r} report found for run {run_id!r} (expected {path})"
        )
    return RunReport.model_validate_json(path.read_text(encoding="utf-8"))


def load_final_report(run_id: str) -> RunReport:
    """Load the pipeline's final (migration-stage) report for `run_id`."""
    return load_stage_report(run_id, "migration")
