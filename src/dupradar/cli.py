"""Typer CLI entrypoint for dupradar (wired via pyproject.toml's `dupradar` script).

Commands:
    dupradar scan --repo id=path [--repo id=path ...]
    dupradar pipeline run
    dupradar dashboard

`dupradar.orchestrator` (and therefore the real agent modules it imports
at its own top level) is only imported inside each command's body, not at
this module's top level. That is deliberate: it keeps `from dupradar.cli
import app` import-safe on its own merits even while a teammate's agent
module is still mid-build -- only *running* a pipeline command needs the
orchestrator to be fully importable, not just loading the CLI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from dupradar.config import DATA_RUNS_DIR, SAMPLE_REPOS_DIR
from dupradar.schemas.reports import RunReport

app = typer.Typer(help="dupradar - multi-repo code duplication resolver")
pipeline_app = typer.Typer(help="Pipeline-related commands.")
app.add_typer(pipeline_app, name="pipeline")

DASHBOARD_APP_PATH = Path(__file__).resolve().parent / "dashboard" / "app.py"

SAMPLE_REPO_IDS = ("repo_a_payments", "repo_b_orders", "repo_c_inventory")


def _sample_repo_pairs() -> list[tuple[str, str]]:
    return [(repo_id, str(SAMPLE_REPOS_DIR / repo_id)) for repo_id in SAMPLE_REPO_IDS]


def _parse_repo_options(repo_options: list[str]) -> list[tuple[str, str]]:
    """Parse repeated `--repo id=path` options into (repo_id, path) pairs."""
    repos: list[tuple[str, str]] = []
    for item in repo_options:
        repo_id, sep, path = item.partition("=")
        if not sep or not repo_id or not path:
            raise typer.BadParameter(
                f"--repo must be in the form id=path, got {item!r}"
            )
        repos.append((repo_id, path))
    return repos


def _echo_result(report: RunReport) -> None:
    final_path = DATA_RUNS_DIR / report.run_id / "final_report.json"
    typer.echo(f"run_id: {report.run_id}")
    typer.echo(f"final report: {final_path}")


@app.command()
def scan(
    repo: list[str] = typer.Option(
        ...,
        "--repo",
        help="Repo to analyze, as id=path. Repeat for multiple repos, "
        "e.g. --repo repo_a_payments=./sample_repos/repo_a_payments",
    ),
    run_id: str | None = typer.Option(
        None, "--run-id", help="Reuse a specific run id instead of generating one."
    ),
) -> None:
    """Run the full 4-stage pipeline against the given repos."""
    from dupradar.orchestrator import run_pipeline

    repos = _parse_repo_options(repo)
    report = run_pipeline(repos, run_id=run_id)
    _echo_result(report)


@pipeline_app.command("run")
def pipeline_run(
    run_id: str | None = typer.Option(
        None, "--run-id", help="Reuse a specific run id instead of generating one."
    ),
) -> None:
    """Run the full pipeline against the 3 built-in sample_repos."""
    from dupradar.orchestrator import run_pipeline

    report = run_pipeline(_sample_repo_pairs(), run_id=run_id)
    _echo_result(report)


@app.command()
def dashboard() -> None:
    """Launch the Streamlit dashboard over past pipeline runs."""
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(DASHBOARD_APP_PATH)])


if __name__ == "__main__":
    app()
