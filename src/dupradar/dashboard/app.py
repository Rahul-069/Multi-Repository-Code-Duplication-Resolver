"""Single-page Streamlit dashboard over a dupradar pipeline run.

Run via `dupradar dashboard` (shells out to `streamlit run` on this file),
or directly with `streamlit run src/dupradar/dashboard/app.py`.

Reads only `data/runs/<run_id>/final_report.json` (via `load_final_report`)
-- no DB, no live agent/MCP calls from this process.
"""

from __future__ import annotations

import streamlit as st

from dupradar.config import DATA_RUNS_DIR
from dupradar.storage.run_store import load_final_report

st.set_page_config(page_title="dupradar", layout="wide")
st.title("dupradar — duplication report")

existing_runs = (
    sorted((p.name for p in DATA_RUNS_DIR.iterdir() if p.is_dir()), reverse=True)
    if DATA_RUNS_DIR.exists()
    else []
)

if existing_runs:
    choice = st.selectbox("Run", ["(enter manually)"] + existing_runs)
    default_run_id = "" if choice == "(enter manually)" else choice
else:
    st.info(f"No runs found yet under {DATA_RUNS_DIR}.")
    default_run_id = ""

run_id = st.text_input("Run ID", value=default_run_id)

if not run_id:
    st.warning("Enter or select a run_id to view its report.")
    st.stop()

try:
    report = load_final_report(run_id)
except FileNotFoundError:
    st.warning(f"No report found for run_id {run_id!r}.")
    st.stop()
except Exception as exc:  # malformed report on disk, etc. -- surface, don't crash
    st.warning(f"Could not load report for run_id {run_id!r}: {exc}")
    st.stop()

# --- summary row ---
total_clusters = len(report.clusters)
total_duplicated_loc = sum(
    function.loc for cluster in report.clusters for function in cluster.functions
)
total_hours_saved = sum(
    cluster.impact.maintenance_savings_hours_per_year
    for cluster in report.clusters
    if cluster.impact is not None
)

col1, col2, col3 = st.columns(3)
col1.metric("Total clusters", total_clusters)
col2.metric("Total duplicated LOC", total_duplicated_loc)
col3.metric("Est. hours/year saved", f"{total_hours_saved:.1f}")

st.divider()

if not report.clusters:
    st.info("No duplicate clusters found for this run.")

for cluster in report.clusters:
    header = (
        f"Cluster {cluster.cluster_id} "
        f"({cluster.match_type}, similarity={cluster.similarity})"
    )
    with st.expander(header):
        st.subheader("Member functions")
        st.table(
            [
                {
                    "repo_id": function.repo_id,
                    "qualified_name": function.qualified_name,
                    "file_path": function.file_path,
                    "lines": f"{function.start_line}-{function.end_line}",
                }
                for function in cluster.functions
            ]
        )

        st.subheader("Proposed abstraction")
        if cluster.proposed_abstraction is not None:
            abstraction = cluster.proposed_abstraction
            st.markdown(f"**{abstraction.api_name}**")
            st.code(abstraction.signature_sketch, language="python")
            st.write(abstraction.rationale)
            st.caption(f"Security notes: {abstraction.security_notes}")
        else:
            st.write("_Not available._")

        st.subheader("Impact")
        if cluster.impact is not None:
            impact = cluster.impact
            st.write(
                f"Maintenance savings: {impact.maintenance_savings_hours_per_year:.1f} hrs/year  \n"
                f"Tech debt score: {impact.tech_debt_score:.1f}  \n"
                f"Consolidation risk: {impact.consolidation_risk}  \n"
                f"Priority rank: {impact.priority_rank}"
            )
            if impact.risk_reasons:
                st.write("Risk reasons:")
                for reason in impact.risk_reasons:
                    st.write(f"- {reason}")
        else:
            st.write("_Not available._")

        st.subheader("Migration plan")
        if cluster.migration_plan:
            lines: list[str] = []
            for step in sorted(cluster.migration_plan, key=lambda s: s.step_number):
                lines.append(
                    f"{step.step_number}. **{step.action}** "
                    f"— owning repo: `{step.owning_repo}`"
                )
                lines.append(f"   - PR description: {step.suggested_pr_description}")
                if step.suggested_tests:
                    lines.append(
                        "   - Suggested tests: " + ", ".join(step.suggested_tests)
                    )
                lines.append(f"   - Rollback plan: {step.rollback_plan}")
            st.markdown("\n".join(lines))
        else:
            st.write("_Not available._")

        if cluster.suggested_shared_package_path:
            st.caption(
                f"Suggested shared package path: {cluster.suggested_shared_package_path}"
            )
