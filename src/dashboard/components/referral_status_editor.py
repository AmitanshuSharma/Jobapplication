"""Referral status editor write component.

Renders controls to update referral_status and follow_up_date.
Calls referrals_repository.update_referral_status on save, then st.rerun().

Permitted to import db.referrals_repository directly per DECISIONS.md.
"""
import streamlit as st

from src.db.connection import get_connection
from src.db import referrals_repository

_REFERRAL_STATUSES = ["", "Pending", "Confirmed", "Declined", "No response"]


def render_referral_status_editor(
    referral_id: int,
    current_status: str | None,
    current_follow_up_date: str | None,
    config: dict,
) -> None:
    """Render referral status and follow-up date editor.

    Args:
        referral_id: Integer primary key of the referral record.
        current_status: Current referral_status string or None.
        current_follow_up_date: ISO-8601 date string or None.
        config: Config dict containing database_path.
    """
    status_idx = (
        _REFERRAL_STATUSES.index(current_status)
        if current_status in _REFERRAL_STATUSES
        else 0
    )
    new_status = st.selectbox(
        "Referral status",
        options=_REFERRAL_STATUSES,
        index=status_idx,
        key=f"ref_status_{referral_id}",
    )

    follow_up_value = None
    if current_follow_up_date:
        try:
            from datetime import date
            parts = current_follow_up_date.split("-")
            follow_up_value = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError, AttributeError):
            follow_up_value = None

    new_follow_up = st.date_input(
        "Follow-up date",
        value=follow_up_value,
        key=f"ref_followup_{referral_id}",
    )

    if st.button("Save", key=f"ref_save_{referral_id}"):
        follow_up_str = str(new_follow_up) if new_follow_up else None
        conn = get_connection(config["database_path"])
        try:
            referrals_repository.update_referral_status(
                referral_id, new_status or None, follow_up_str, conn
            )
        finally:
            conn.close()
        st.rerun()
