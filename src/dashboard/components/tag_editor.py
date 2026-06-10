"""Tag editor write component.

Renders a text input for comma-separated tags and a save button.
Empty input clears all tags. Calls jobs_repository.update_job_tags on save.

Allowed imports: streamlit, src.db.jobs_repository, src.db.connection.
"""
import streamlit as st

from src.db.connection import get_connection
from src.db import jobs_repository


def render_tag_editor(job_id: int, current_tags: str, config: dict) -> None:
    """Render tag text input and save button for the given job.

    Args:
        job_id: Integer primary key of the job record.
        current_tags: Comma-separated tag string or empty string.
        config: Config dict containing database_path.
    """
    new_tags = st.text_input(
        "Tags (comma-separated)",
        value=current_tags or "",
        key=f"tags_input_{job_id}",
    )
    if st.button("Save tags", key=f"tags_save_{job_id}"):
        conn = get_connection(config["database_path"])
        try:
            jobs_repository.update_job_tags(job_id, new_tags, conn)
        finally:
            conn.close()
        st.rerun()
