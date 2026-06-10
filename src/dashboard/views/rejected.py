"""Rejected view — jobs with status='Rejected'.

Status editor is constrained to Pending only (undo path).
Columns: title, company, score, first_seen_at.
Export: CSV + Excel (per DECISIONS.md — Rejected View Exports).
"""
import streamlit as st

from src.dashboard import data_loader
from src.dashboard.components import job_table, score_breakdown
from src.db.connection import get_connection
from src.db import jobs_repository
from src.export import exporter

_COLUMNS = ["title", "company", "score", "first_seen_at"]


def render(config: dict) -> None:
    """Render the Rejected view."""
    st.subheader("Rejected")

    df = data_loader.load_jobs_by_status("Rejected", config)

    total = len(df)
    if total > 200:
        st.info(f"Showing 200 of {total} records.")
        df = df.head(200)

    selected = job_table.render_job_table(df, _COLUMNS, config, key="rejected_table")

    if selected:
        st.subheader(selected.get("title", ""))
        st.caption(
            f"{selected.get('company', '')} · {selected.get('location_normalized', '')}"
        )
        st.divider()
        st.caption("Move back to Inbox?")
        if st.button("Undo — move to Pending", key=f"undo_{selected['id']}"):
            conn = get_connection(config["database_path"])
            try:
                jobs_repository.update_job_status(selected["id"], "Pending", conn)
            finally:
                conn.close()
            st.rerun()
        score_breakdown.render_score_breakdown(selected.get("score_breakdown"))

    st.write("---")
    if not df.empty:
        col_csv, col_xlsx, _ = st.columns([1, 1, 4])
        with col_csv:
            st.download_button(
                "Download CSV",
                exporter.export_jobs_csv(df),
                "rejected.csv",
                "text/csv",
                key="rejected_csv",
            )
        with col_xlsx:
            st.download_button(
                "Download Excel",
                exporter.export_jobs_excel(df),
                "rejected.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="rejected_xlsx",
            )
