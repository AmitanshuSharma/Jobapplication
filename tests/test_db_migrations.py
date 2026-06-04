"""Tests for src/db/migrations.py. All tests use tmp_path — no production DB touched."""
import sqlite3

import pytest

from src.db.connection import get_connection
from src.db.migrations import run_migrations


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


def test_creates_jobs_table(db_path):
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_creates_referrals_table(db_path):
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='referrals'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_creates_schema_version_table(db_path):
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_records_version_1(db_path):
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    conn.close()
    assert row[0] == 1


def test_applied_at_uses_utc_z_format(db_path):
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT applied_at FROM schema_version").fetchone()
    conn.close()
    # Must be UTC ISO-8601 with Z suffix, e.g. "2026-05-28T14:22:11Z"
    assert row[0].endswith("Z")
    assert "T" in row[0]


def test_is_idempotent(db_path):
    run_migrations(db_path)
    run_migrations(db_path)  # must not raise or insert a second row
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    conn.close()
    assert count == 1


def test_wal_mode_enabled(db_path):
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute("PRAGMA journal_mode").fetchone()
    conn.close()
    assert row[0] == "wal"


def test_foreign_key_enforcement_on(db_path):
    # get_connection sets PRAGMA foreign_keys=ON; inserting a referral with a
    # non-existent job_id must raise IntegrityError.
    run_migrations(db_path)
    conn = get_connection(db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO referrals (job_id, company, recruiter_contacted, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (9999, "Acme", 0, "2026-05-28T00:00:00Z", "2026-05-28T00:00:00Z"),
        )
        conn.commit()
    conn.close()


def test_jobs_table_has_created_at_and_updated_at(db_path):
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    info = conn.execute("PRAGMA table_info(jobs)").fetchall()
    conn.close()
    column_names = [row[1] for row in info]
    assert "created_at" in column_names
    assert "updated_at" in column_names
    assert "source_name" in column_names


def test_status_score_composite_index_exists(db_path):
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_jobs_status_score'"
    ).fetchone()
    conn.close()
    assert row is not None
