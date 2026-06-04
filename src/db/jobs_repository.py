import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_INSERT_JOB_SQL = """
    INSERT INTO jobs (
        source_url, ats_job_id, dedup_hash, title, company,
        location, location_normalized, description, experience_range,
        tech_stack, score, score_breakdown, passed_threshold, status,
        tags, notified, location_ineligible, first_seen_at, date_posted,
        source_name, created_at, updated_at
    ) VALUES (
        :source_url, :ats_job_id, :dedup_hash, :title, :company,
        :location, :location_normalized, :description, :experience_range,
        :tech_stack, :score, :score_breakdown, :passed_threshold, :status,
        :tags, :notified, :location_ineligible, :first_seen_at, :date_posted,
        :source_name, :created_at, :updated_at
    )
"""


def insert_job(job_record: dict, conn: sqlite3.Connection) -> int:
    """Insert a new job record. Returns the new row's integer id.

    Sets created_at and updated_at to the current UTC time internally.
    Does not mutate the input dict.
    """
    now = _utc_now()
    record = {**job_record, "created_at": now, "updated_at": now}
    cursor = conn.execute(_INSERT_JOB_SQL, record)
    conn.commit()
    return cursor.lastrowid


def job_exists_by_dedup_key(
    source_url: str,
    ats_job_id: str | None,
    dedup_hash: str | None,
    conn: sqlite3.Connection,
) -> bool:
    """Return True if a matching job already exists.

    Three-priority check per DECISIONS.md:
    1. ATS Job ID + Source URL
    2. Source URL alone — a URL uniquely identifies one posting
    3. dedup_hash — SHA-256 of company+title+location_normalized (no ats_job_id case)
    """
    if ats_job_id:
        row = conn.execute(
            "SELECT id FROM jobs WHERE source_url = ? AND ats_job_id = ?",
            (source_url, ats_job_id),
        ).fetchone()
        if row:
            return True

    row = conn.execute(
        "SELECT id FROM jobs WHERE source_url = ?",
        (source_url,),
    ).fetchone()
    if row:
        return True

    if dedup_hash:
        row = conn.execute(
            "SELECT id FROM jobs WHERE dedup_hash = ?",
            (dedup_hash,),
        ).fetchone()
        if row:
            return True

    return False


def get_job_by_id(job_id: int, conn: sqlite3.Connection) -> dict | None:
    """Return the full job record as a dict, or None if not found."""
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_jobs_by_status(status: str, conn: sqlite3.Connection) -> list[dict]:
    """Return all job records with the given status, ordered by score descending."""
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status = ? ORDER BY score DESC",
        (status,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_notification_candidates(threshold: int, conn: sqlite3.Connection) -> list[dict]:
    """Return jobs eligible for notification: notified=0, location_ineligible=0,
    score >= threshold. Ordered by score descending.
    """
    rows = conn.execute(
        """
        SELECT * FROM jobs
        WHERE notified = 0
          AND location_ineligible = 0
          AND score >= ?
        ORDER BY score DESC
        """,
        (threshold,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_job_status(job_id: int, new_status: str, conn: sqlite3.Connection) -> None:
    """Update status and refresh updated_at."""
    conn.execute(
        "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, _utc_now(), job_id),
    )
    conn.commit()


def update_job_tags(job_id: int, tags: str, conn: sqlite3.Connection) -> None:
    """Update tags and refresh updated_at. Empty string clears tags."""
    conn.execute(
        "UPDATE jobs SET tags = ?, updated_at = ? WHERE id = ?",
        (tags, _utc_now(), job_id),
    )
    conn.commit()


def mark_notified(job_id: int, conn: sqlite3.Connection) -> None:
    """Set notified=1 and refresh updated_at."""
    conn.execute(
        "UPDATE jobs SET notified = 1, updated_at = ? WHERE id = ?",
        (_utc_now(), job_id),
    )
    conn.commit()
