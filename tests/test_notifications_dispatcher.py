"""Tests for src/notifications/dispatcher.py.

Uses a real in-memory SQLite DB (migrated) with mocked transport modules.
Connection lifecycle owned by the test fixture.
"""
import json

import pytest
from unittest.mock import patch

from src.db.connection import get_connection
from src.db.migrations import run_migrations
from src.db.jobs_repository import insert_job
from src.notifications.dispatcher import dispatch_new_jobs


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    """Migrated SQLite connection. Caller owns lifecycle."""
    db_path = str(tmp_path / "test.db")
    run_migrations(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


CONFIG = {
    "notification_threshold": 20,
    "TELEGRAM_BOT_TOKEN": "test-token",
    "TELEGRAM_CHAT_ID": "12345",
    "EMAIL_ADDRESS": "test@example.com",
    "EMAIL_PASSWORD": "password",
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
}


def _make_job(**overrides):
    """Return a minimal valid job record dict. Repository sets created_at/updated_at."""
    base = {
        "source_url": "https://example.com/job/1",
        "ats_job_id": "job-001",
        "dedup_hash": None,
        "title": "Senior Data Engineer",
        "company": "Stripe",
        "location": "Remote",
        "location_normalized": "Remote",
        "description": "Build pipelines.",
        "experience_range": None,
        "tech_stack": None,
        "source_name": "greenhouse",
        "score": 25,
        "score_breakdown": json.dumps({
            "components": [{"label": "PySpark", "points": 25}],
            "role_match": True,
            "matched_positive_keywords": ["PySpark"],
            "matched_negative_keywords": [],
            "final_score": 25,
            "threshold_at_ingestion": 20,
        }),
        "passed_threshold": 1,
        "status": "Pending",
        "tags": None,
        "notified": 0,
        "location_ineligible": 0,
        "first_seen_at": "2026-06-09T10:00:00Z",
        "date_posted": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_both_channels_succeed(conn):
    insert_job(_make_job(), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=True), \
         patch("src.notifications.dispatcher.send_email", return_value=True):
        result = dispatch_new_jobs(CONFIG, conn)
    assert result == {"eligible": 1, "attempted": 1, "notified": 1, "both_failed": 0}


def test_telegram_succeeds_email_fails(conn):
    insert_job(_make_job(), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=True), \
         patch("src.notifications.dispatcher.send_email", return_value=False):
        result = dispatch_new_jobs(CONFIG, conn)
    assert result["notified"] == 1
    assert result["both_failed"] == 0


def test_telegram_fails_email_succeeds(conn):
    insert_job(_make_job(), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=False), \
         patch("src.notifications.dispatcher.send_email", return_value=True):
        result = dispatch_new_jobs(CONFIG, conn)
    assert result["notified"] == 1
    assert result["both_failed"] == 0


def test_both_channels_fail(conn):
    insert_job(_make_job(), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=False), \
         patch("src.notifications.dispatcher.send_email", return_value=False):
        result = dispatch_new_jobs(CONFIG, conn)
    assert result == {"eligible": 1, "attempted": 1, "notified": 0, "both_failed": 1}


def test_already_notified_job_not_dispatched(conn):
    insert_job(_make_job(notified=1), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=True) as mock_tg, \
         patch("src.notifications.dispatcher.send_email", return_value=True) as mock_em:
        result = dispatch_new_jobs(CONFIG, conn)
    assert result["eligible"] == 0
    mock_tg.assert_not_called()
    mock_em.assert_not_called()


def test_below_threshold_not_dispatched(conn):
    insert_job(_make_job(score=5, passed_threshold=0), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=True) as mock_tg, \
         patch("src.notifications.dispatcher.send_email", return_value=True) as mock_em:
        result = dispatch_new_jobs(CONFIG, conn)
    assert result["eligible"] == 0
    mock_tg.assert_not_called()
    mock_em.assert_not_called()


def test_location_ineligible_not_dispatched(conn):
    insert_job(_make_job(location_ineligible=1), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=True) as mock_tg, \
         patch("src.notifications.dispatcher.send_email", return_value=True) as mock_em:
        result = dispatch_new_jobs(CONFIG, conn)
    assert result["eligible"] == 0
    mock_tg.assert_not_called()
    mock_em.assert_not_called()


def test_empty_eligible_set(conn):
    result = dispatch_new_jobs(CONFIG, conn)
    assert result == {"eligible": 0, "attempted": 0, "notified": 0, "both_failed": 0}


def test_multiple_jobs_mixed_results(conn):
    insert_job(_make_job(source_url="https://example.com/job/1", ats_job_id="j1"), conn)
    insert_job(_make_job(source_url="https://example.com/job/2", ats_job_id="j2"), conn)

    call_count = [0]

    def tg_side_effect(job, cfg):
        call_count[0] += 1
        return call_count[0] == 1  # True for first job only

    with patch("src.notifications.dispatcher.send_telegram", side_effect=tg_side_effect), \
         patch("src.notifications.dispatcher.send_email", return_value=False):
        result = dispatch_new_jobs(CONFIG, conn)

    assert result["eligible"] == 2
    assert result["attempted"] == 2
    assert result["notified"] == 1
    assert result["both_failed"] == 1


def test_dispatcher_marks_notified_only_once(conn):
    """A notified job must not be dispatched again on a second call."""
    insert_job(_make_job(), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=True) as mock_tg, \
         patch("src.notifications.dispatcher.send_email", return_value=True) as mock_em:
        result1 = dispatch_new_jobs(CONFIG, conn)
        result2 = dispatch_new_jobs(CONFIG, conn)

    assert result1["notified"] == 1
    assert result2["eligible"] == 0
    assert mock_tg.call_count == 1
    assert mock_em.call_count == 1


def test_both_channels_always_attempted_independently(conn):
    """Email is always attempted even when Telegram fails."""
    insert_job(_make_job(), conn)
    with patch("src.notifications.dispatcher.send_telegram", return_value=False) as mock_tg, \
         patch("src.notifications.dispatcher.send_email", return_value=True) as mock_em:
        dispatch_new_jobs(CONFIG, conn)
    mock_tg.assert_called_once()
    mock_em.assert_called_once()
