"""Applied view — jobs with status='Applied'.

Columns: score, title, company, location_normalized, date_posted, first_seen_at, tags.
Edit panel: status editor + tag editor + score breakdown.
Export: CSV + Excel.
"""
import streamlit as st

from src.dashboard import data_loader
from src.dashboard.components import (
    job_table,
    score_breakdown,
    status_editor,
    tag_editor,
)
from src.export import exporter

_COLUMNS = [
    "score", "title", "company", "location_normalized",
    "date_posted", "first_seen_at", "tags",
]


def render(config: dict) -> None:
    """Render the Applied view."""
    st.subheader("Applied")

    df = data_loader.load_jobs_by_status("Applied", config)

    total = len(df)
    if total > 200:
        st.info(f"Showing 200 of {total} records.")
        df = df.head(200)

    selected = job_table.render_job_table(df, _COLUMNS, config, key="applied_table")

    if selected:
        st.subheader(selected.get("title", ""))
        st.caption(
            f"{selected.get('company', '')} · {selected.get('location_normalized', '')}"
        )
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            status_editor.render_status_editor(
                selected["id"], selected.get("status", "Applied"), config
            )
        with col2:
            tag_editor.render_tag_editor(
                selected["id"], selected.get("tags") or "", config
            )
        score_breakdown.render_score_breakdown(selected.get("score_breakdown"))

    st.write("---")
    if not df.empty:
        col_csv, col_xlsx, _ = st.columns([1, 1, 4])
        with col_csv:
            st.download_button(
                "Download CSV",
                exporter.export_jobs_csv(df),
                "applied.csv",
                "text/csv",
                key="applied_csv",
            )
        with col_xlsx:
            st.download_button(
                "Download Excel",
                exporter.export_jobs_excel(df),
                "applied.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="applied_xlsx",
            )
