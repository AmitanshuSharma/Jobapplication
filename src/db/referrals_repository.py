import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_INSERT_REFERRAL_SQL = """
    INSERT INTO referrals (
        job_id, company, role, applied_date, referral_status,
        recruiter_contacted, follow_up_date, notes, created_at, updated_at
    ) VALUES (
        :job_id, :company, :role, :applied_date, :referral_status,
        :recruiter_contacted, :follow_up_date, :notes, :created_at, :updated_at
    )
"""

# Nulls-last sort per DECISIONS.md: follow_up_date ASC NULLS LAST, then updated_at DESC.
_SELECT_ALL_SQL = """
    SELECT * FROM referrals
    ORDER BY
        CASE WHEN follow_up_date IS NULL THEN 1 ELSE 0 END,
        follow_up_date ASC,
        updated_at DESC
"""


def insert_referral(referral_record: dict, conn: sqlite3.Connection) -> int:
    """Insert a new referral record. Returns the new row's integer id.

    Sets created_at and updated_at to the current UTC time internally.
    """
    now = _utc_now()
    record = {
        "job_id": referral_record.get("job_id"),
        "company": referral_record["company"],
        "role": referral_record.get("role"),
        "applied_date": referral_record.get("applied_date"),
        "referral_status": referral_record.get("referral_status"),
        "recruiter_contacted": referral_record.get("recruiter_contacted", 0),
        "follow_up_date": referral_record.get("follow_up_date"),
        "notes": referral_record.get("notes"),
        "created_at": now,
        "updated_at": now,
    }
    cursor = conn.execute(_INSERT_REFERRAL_SQL, record)
    conn.commit()
    return cursor.lastrowid


def get_referral_by_id(referral_id: int, conn: sqlite3.Connection) -> dict | None:
    """Return the full referral record as a dict, or None if not found."""
    row = conn.execute(
        "SELECT * FROM referrals WHERE id = ?", (referral_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_referrals(conn: sqlite3.Connection) -> list[dict]:
    """Return all referral records sorted by follow_up_date ASC (NULLs last),
    then updated_at DESC (DECISIONS.md).
    """
    rows = conn.execute(_SELECT_ALL_SQL).fetchall()
    return [dict(r) for r in rows]


def update_referral_status(
    referral_id: int,
    referral_status: str,
    follow_up_date: str | None,
    conn: sqlite3.Connection,
) -> None:
    """Update referral_status, follow_up_date, and updated_at for the given id."""
    conn.execute(
        """
        UPDATE referrals
        SET referral_status = ?, follow_up_date = ?, updated_at = ?
        WHERE id = ?
        """,
        (referral_status, follow_up_date, _utc_now(), referral_id),
    )
    conn.commit()
