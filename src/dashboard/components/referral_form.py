"""Referral form write component.

Renders a 'New Referral' button that expands an inline form.
Required field: company. All other fields are optional.
Calls referrals_repository.insert_referral on submit, then st.rerun().

Allowed imports: streamlit, src.db.referrals_repository, src.db.connection.
"""
import streamlit as st

from src.db.connection import get_connection
from src.db import referrals_repository

_REFERRAL_STATUSES = ["", "Pending", "Confirmed", "Declined", "No response"]


def render_referral_form(config: dict) -> None:
    """Render a 'New Referral' button and inline form.

    Args:
        config: Config dict containing database_path.
    """
    if "show_referral_form" not in st.session_state:
        st.session_state["show_referral_form"] = False

    if st.button("+ New Referral", key="new_referral_btn"):
        st.session_state["show_referral_form"] = not st.session_state["show_referral_form"]

    if not st.session_state["show_referral_form"]:
        return

    with st.form("referral_form", clear_on_submit=True):
        st.markdown("**New Referral**")
        company = st.text_input("Company *", key="rf_company")
        role = st.text_input("Role", key="rf_role")

        col1, col2 = st.columns(2)
        with col1:
            applied_date = st.date_input("Applied date", value=None, key="rf_applied_date")
        with col2:
            follow_up_date = st.date_input("Follow-up date", value=None, key="rf_followup")

        referral_status = st.selectbox(
            "Referral status", options=_REFERRAL_STATUSES, key="rf_status"
        )
        recruiter_contacted = st.checkbox("Recruiter contacted", key="rf_recruiter")
        notes = st.text_area("Notes", key="rf_notes")

        submitted = st.form_submit_button("Save referral")

    if submitted:
        if not company.strip():
            st.error("Company is required.")
            return

        record = {
            "company": company.strip(),
            "role": role.strip() or None,
            "applied_date": str(applied_date) if applied_date else None,
            "follow_up_date": str(follow_up_date) if follow_up_date else None,
            "referral_status": referral_status or None,
            "recruiter_contacted": 1 if recruiter_contacted else 0,
            "notes": notes.strip() or None,
            "job_id": None,
        }
        conn = get_connection(config["database_path"])
        try:
            referrals_repository.insert_referral(record, conn)
        finally:
            conn.close()
        st.session_state["show_referral_form"] = False
        st.rerun()
