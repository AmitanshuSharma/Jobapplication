"""Referrals view — all rows from the referrals table.

Columns: company, role, referral_status, recruiter_contacted,
         follow_up_date, applied_date, notes.
Actions: create new referral, update status + follow-up date.
Export: CSV + Excel.
"""
import streamlit as st

from src.dashboard import data_loader
from src.dashboard.components import (
    referral_form,
    referral_status_editor,
)
from src.export import exporter
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

_COLUMNS = [
    "company", "role", "referral_status", "recruiter_contacted",
    "follow_up_date", "applied_date", "notes",
]

_NOTES_MAX = 60


def _truncate_notes(df):
    """Truncate notes column for table display."""
    import pandas as pd
    df = df.copy()
    if "notes" in df.columns:
        df["notes"] = df["notes"].apply(
            lambda v: (str(v)[:_NOTES_MAX] + "…") if v and len(str(v)) > _NOTES_MAX else v
        )
    return df


def render(config: dict) -> None:
    """Render the Referrals view."""
    st.subheader("Referrals")

    referral_form.render_referral_form(config)

    df = data_loader.load_all_referrals(config)

    if df.empty:
        st.info("No referral records yet.")
        return

    display_df = _truncate_notes(df)
    display_cols = [c for c in _COLUMNS if c in display_df.columns]
    carry_cols = [c for c in ["id"] if c not in display_cols and c in display_df.columns]
    grid_df = display_df[display_cols + carry_cols].copy()

    gb = GridOptionsBuilder.from_dataframe(grid_df)
    gb.configure_default_column(resizable=True, sortable=True, filter=True)
    gb.configure_selection("single", use_checkbox=False)
    for col in carry_cols:
        gb.configure_column(col, hide=True)

    response = AgGrid(
        grid_df,
        gridOptions=gb.build(),
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        theme="streamlit",
        height=380,
        fit_columns_on_grid_load=True,
        key="referrals_table",
    )

    selected_rows = response["selected_rows"]
    if selected_rows is not None and len(selected_rows) > 0:
        selected = dict(selected_rows[0])
        st.subheader(selected.get("company", ""))
        st.caption(selected.get("role") or "")
        st.divider()
        referral_status_editor.render_referral_status_editor(
            referral_id=selected["id"],
            current_status=selected.get("referral_status"),
            current_follow_up_date=selected.get("follow_up_date"),
            config=config,
        )

    st.write("---")
    col_csv, col_xlsx, _ = st.columns([1, 1, 4])
    with col_csv:
        st.download_button(
            "Download CSV",
            exporter.export_referrals_csv(df),
            "referrals.csv",
            "text/csv",
            key="referrals_csv",
        )
    with col_xlsx:
        st.download_button(
            "Download Excel",
            exporter.export_referrals_excel(df),
            "referrals.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="referrals_xlsx",
        )
