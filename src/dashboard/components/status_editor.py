"""Status editor write component.

Renders a status dropdown and save button for a single job.
Calls jobs_repository.update_job_status on save, then st.rerun().

Allowed imports: streamlit, src.db.jobs_repository, src.db.connection.
"""
import streamlit as st

from src.db.connection import get_connection
from src.db import jobs_repository

_VALID_STATUSES = ["Pending", "Applied", "Referral-Needed", "Rejected"]


def render_status_editor(job_id: int, current_status: str, config: dict) -> None:
    """Render status dropdown and save button for the given job.

    Args:
        job_id: Integer primary key of the job record.
        current_status: The job's current status string.
        config: Config dict containing database_path.
    """
    current_idx = (
        _VALID_STATUSES.index(current_status)
        if current_status in _VALID_STATUSES
        else 0
    )
    new_status = st.selectbox(
        "Status",
        options=_VALID_STATUSES,
        index=current_idx,
        key=f"status_select_{job_id}",
    )
    if st.button("Save status", key=f"status_save_{job_id}"):
        conn = get_connection(config["database_path"])
        try:
            jobs_repository.update_job_status(job_id, new_status, conn)
        finally:
            conn.close()
        st.rerun()
