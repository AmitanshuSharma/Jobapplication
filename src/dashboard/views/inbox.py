"""Inbox view — jobs with status='Pending'.

Columns: score, title, company, source_name, location_normalized, first_seen_at, tags.
Edit panel: status editor + tag editor + score breakdown.
Export: CSV + Excel.
"""
import streamlit as st

from src.dashboard import data_loader
from src.dashboard.components import (
    filters,
    job_table,
    score_breakdown,
    status_editor,
    tag_editor,
)
from src.export import exporter

_COLUMNS = [
    "score", "title", "company", "source_name",
    "location_normalized", "first_seen_at", "tags",
]


def render(config: dict) -> None:
    """Render the Inbox view.

    Args:
        config: Loaded config dict.
    """
    st.subheader("Inbox")

    df = data_loader.load_inbox_jobs(config)

    if not df.empty:
        filtered_df = filters.render_pre_filters(df)
    else:
        filtered_df = df

    total = len(filtered_df)
    if total > 200:
        st.info(f"Showing 200 of {total} records. Refine filters to see more.")
        filtered_df = filtered_df.head(200)

    selected = job_table.render_job_table(
        filtered_df, _COLUMNS, config, key="inbox_table"
    )

    if selected:
        st.subheader(selected.get("title", ""))
        st.caption(
            f"{selected.get('company', '')} · {selected.get('location_normalized', '')}"
        )
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            status_editor.render_status_editor(
                selected["id"], selected.get("status", "Pending"), config
            )
        with col2:
            tag_editor.render_tag_editor(
                selected["id"], selected.get("tags") or "", config
            )
        score_breakdown.render_score_breakdown(selected.get("score_breakdown"))

    st.write("---")
    if not filtered_df.empty:
        col_csv, col_xlsx, _ = st.columns([1, 1, 4])
        with col_csv:
            st.download_button(
                "Download CSV",
                exporter.export_jobs_csv(filtered_df),
                "inbox.csv",
                "text/csv",
                key="inbox_csv",
            )
        with col_xlsx:
            st.download_button(
                "Download Excel",
                exporter.export_jobs_excel(filtered_df),
                "inbox.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="inbox_xlsx",
            )
