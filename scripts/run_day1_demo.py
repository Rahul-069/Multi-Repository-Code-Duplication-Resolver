"""End-to-end Day 1 demo: run the full dupradar pipeline against the 3
built-in sample repos and report what it found.

Usage:
    python scripts/run_day1_demo.py

Zero required args. This is the command used for end-of-day verification:
it prints a run_id, the path to that run's final_report.json, and a
one-line summary of the clusters found.
"""

from __future__ import annotations

from dupradar.config import DATA_RUNS_DIR, SAMPLE_REPOS_DIR
from dupradar.orchestrator import run_pipeline

SAMPLE_REPO_IDS = ("repo_a_payments", "repo_b_orders", "repo_c_inventory")


def main() -> None:
    repos = [(repo_id, str(SAMPLE_REPOS_DIR / repo_id)) for repo_id in SAMPLE_REPO_IDS]

    report = run_pipeline(repos)

    final_path = DATA_RUNS_DIR / report.run_id / "final_report.json"

    print(f"run_id: {report.run_id}")
    print(f"final report: {final_path}")

    cluster_count = len(report.clusters)
    repo_summary = ", ".join(report.repos)
    print(
        f"Found {cluster_count} duplicate cluster(s) across {len(report.repos)} "
        f"repo(s) ({repo_summary})."
    )


if __name__ == "__main__":
    main()
