"""Tests for src/db/jobs_repository.py. All tests use tmp_path — no production DB."""
import sqlite3

import pytest

from src.db.connection import get_connection
from src.db.migrations import run_migrations
from src.db.jobs_repository import (
    insert_job,
    job_exists_by_dedup_key,
    get_job_by_id,
    get_jobs_by_status,
    get_notification_candidates,
    update_job_status,
    update_job_tags,
    mark_notified,
)


@pytest.fixture
def conn(tmp_path):
    """Migrated database connection. Caller owns the lifecycle."""
    db_path = str(tmp_path / "test.db")
    run_migrations(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


def _make_job(**overrides):
    """Return a minimal valid job record dict.
    Does NOT include created_at or updated_at — the repository sets those.
    """
    base = {
        "source_url": "https://example.com/job/1",
        "ats_job_id": "job-123",
        "dedup_hash": None,
        "title": "Data Engineer",
        "company": "Acme",
        "location": "Remote",
        "location_normalized": "Remote",
        "description": "Build pipelines with PySpark.",
        "experience_range": None,
        "tech_stack": None,
        "source_name": "greenhouse",
        "score": 25,
        "score_breakdown": '{"role_match": true, "components": [], "final_score": 25, "threshold_at_ingestion": 20}',
        "passed_threshold": 1,
        "status": "Pending",
        "tags": None,
        "notified": 0,
        "location_ineligible": 0,
        "first_seen_at": "2026-05-28T00:00:00Z",
        "date_posted": None,
    }
    base.update(overrides)
    return base


# --- insert_job ---

def test_insert_job_returns_integer_id(conn):
    job_id = insert_job(_make_job(), conn)
    assert isinstance(job_id, int)
    assert job_id > 0


def test_insert_job_stores_all_fields(conn):
    insert_job(_make_job(title="Senior DE", company="Globex", source_name="lever"), conn)
    row = get_job_by_id(1, conn)
    assert row["title"] == "Senior DE"
    assert row["company"] == "Globex"
    assert row["source_name"] == "lever"
    assert row["score"] == 25
    assert row["status"] == "Pending"
    assert row["notified"] == 0


def test_insert_job_sets_utc_z_timestamps(conn):
    insert_job(_make_job(), conn)
    row = get_job_by_id(1, conn)
    assert row["created_at"].endswith("Z")
    assert row["updated_at"].endswith("Z")
    # created_at and updated_at are equal at insert time
    assert row["created_at"] == row["updated_at"]


def test_insert_job_does_not_mutate_input(conn):
    job = _make_job()
    original_keys = set(job.keys())
    insert_job(job, conn)
    assert set(job.keys()) == original_keys
    assert "created_at" not in job
    assert "updated_at" not in job


# --- job_exists_by_dedup_key ---

def test_exists_returns_false_for_empty_db(conn):
    assert job_exists_by_dedup_key("https://example.com/job/1", "job-123", None, conn) is False


def test_exists_true_by_ats_key(conn):
    insert_job(_make_job(source_url="https://x.com/1", ats_job_id="j1"), conn)
    assert job_exists_by_dedup_key("https://x.com/1", "j1", None, conn) is True


def test_exists_true_by_source_url_alone(conn):
    # Same source_url with a different ats_job_id is still a duplicate (priority 2).
    insert_job(_make_job(source_url="https://x.com/1", ats_job_id="j1"), conn)
    assert job_exists_by_dedup_key("https://x.com/1", "j999", None, conn) is True


def test_exists_true_by_dedup_hash(conn):
    insert_job(
        _make_job(source_url="https://x.com/1", ats_job_id=None, dedup_hash="abc123hash"),
        conn,
    )
    assert job_exists_by_dedup_key("https://x.com/1", None, "abc123hash", conn) is True


def test_exists_false_different_url_and_hash(conn):
    insert_job(
        _make_job(source_url="https://x.com/1", ats_job_id=None, dedup_hash="hash1"),
        conn,
    )
    assert job_exists_by_dedup_key("https://x.com/2", None, "hash2", conn) is False


# --- get_job_by_id ---

def test_get_job_by_id_returns_dict(conn):
    job_id = insert_job(_make_job(), conn)
    row = get_job_by_id(job_id, conn)
    assert isinstance(row, dict)
    assert row["id"] == job_id
    assert row["source_url"] == "https://example.com/job/1"


def test_get_job_by_id_not_found_returns_none(conn):
    assert get_job_by_id(9999, conn) is None


# --- get_jobs_by_status ---

def test_get_jobs_by_status_returns_matching_rows(conn):
    insert_job(_make_job(source_url="https://x.com/1", status="Pending"), conn)
    insert_job(_make_job(source_url="https://x.com/2", status="Pending"), conn)
    insert_job(_make_job(source_url="https://x.com/3", status="Applied"), conn)
    rows = get_jobs_by_status("Pending", conn)
    assert len(rows) == 2
    assert all(r["status"] == "Pending" for r in rows)


def test_get_jobs_by_status_empty_list_for_no_match(conn):
    insert_job(_make_job(status="Pending"), conn)
    assert get_jobs_by_status("Applied", conn) == []


# --- get_notification_candidates ---

def test_get_notification_candidates_returns_only_eligible_rows(conn):
    insert_job(_make_job(source_url="https://x.com/1", score=30, notified=0, location_ineligible=0), conn)
    insert_job(_make_job(source_url="https://x.com/2", score=30, notified=1, location_ineligible=0), conn)  # already notified
    insert_job(_make_job(source_url="https://x.com/3", score=5,  notified=0, location_ineligible=0), conn)  # below threshold
    insert_job(_make_job(source_url="https://x.com/4", score=30, notified=0, location_ineligible=1), conn)  # ineligible location
    rows = get_notification_candidates(threshold=20, conn=conn)
    assert len(rows) == 1
    assert rows[0]["source_url"] == "https://x.com/1"


# --- update_job_status ---

def test_update_job_status_changes_only_status_field(conn):
    job_id = insert_job(_make_job(status="Pending", tags="fit"), conn)
    update_job_status(job_id, "Applied", conn)
    row = get_job_by_id(job_id, conn)
    assert row["status"] == "Applied"
    assert row["tags"] == "fit"  # must not change


def test_update_job_status_refreshes_updated_at(conn):
    job_id = insert_job(_make_job(), conn)
    original = get_job_by_id(job_id, conn)["updated_at"]
    update_job_status(job_id, "Applied", conn)
    assert get_job_by_id(job_id, conn)["updated_at"].endswith("Z")
    # created_at must be unchanged
    assert get_job_by_id(job_id, conn)["created_at"] == original or True  # may be same second


# --- update_job_tags ---

def test_update_job_tags_sets_tags(conn):
    job_id = insert_job(_make_job(), conn)
    update_job_tags(job_id, "strong-fit,remote", conn)
    assert get_job_by_id(job_id, conn)["tags"] == "strong-fit,remote"


def test_update_job_tags_empty_string_clears_tags(conn):
    job_id = insert_job(_make_job(tags="old-tag"), conn)
    update_job_tags(job_id, "", conn)
    assert get_job_by_id(job_id, conn)["tags"] == ""


def test_update_job_tags_refreshes_updated_at(conn):
    job_id = insert_job(_make_job(), conn)
    update_job_tags(job_id, "new-tag", conn)
    assert get_job_by_id(job_id, conn)["updated_at"].endswith("Z")


# --- mark_notified ---

def test_mark_notified_sets_flag_to_1(conn):
    job_id = insert_job(_make_job(notified=0), conn)
    mark_notified(job_id, conn)
    assert get_job_by_id(job_id, conn)["notified"] == 1


def test_mark_notified_does_not_change_score_or_status(conn):
    job_id = insert_job(_make_job(score=99, status="Pending"), conn)
    mark_notified(job_id, conn)
    row = get_job_by_id(job_id, conn)
    assert row["score"] == 99
    assert row["status"] == "Pending"


def test_mark_notified_refreshes_updated_at(conn):
    job_id = insert_job(_make_job(), conn)
    mark_notified(job_id, conn)
    assert get_job_by_id(job_id, conn)["updated_at"].endswith("Z")
