"""High Priority view — jobs with score >= threshold, status not Applied/Rejected.

Includes Referral-Needed count badge and filter toggle.
Columns: score, title, company, source_name, location_normalized, date_posted, tags.
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
    "location_normalized", "date_posted", "tags",
]


def render(config: dict) -> None:
    """Render the High Priority view.

    Args:
        config: Loaded config dict.
    """
    df = data_loader.load_high_priority_jobs(config)

    # Header with referral-needed count
    total = len(df)
    referral_needed_count = (
        int((df["status"] == "Referral-Needed").sum()) if not df.empty else 0
    )

    header_col, badge_col = st.columns([5, 2])
    with header_col:
        st.subheader("High Priority")
    with badge_col:
        if referral_needed_count > 0:
            st.caption(f"{referral_needed_count} of {total} need referral")

    if not df.empty:
        filtered_df = filters.render_pre_filters(df, show_referral_toggle=True)
    else:
        filtered_df = df

    display_total = len(filtered_df)
    if display_total > 200:
        st.info(f"Showing 200 of {display_total} records. Refine filters to see more.")
        filtered_df = filtered_df.head(200)

    selected = job_table.render_job_table(
        filtered_df, _COLUMNS, config, key="high_priority_table"
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
                "high_priority.csv",
                "text/csv",
                key="hp_csv",
            )
        with col_xlsx:
            st.download_button(
                "Download Excel",
                exporter.export_jobs_excel(filtered_df),
                "high_priority.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="hp_xlsx",
            )
