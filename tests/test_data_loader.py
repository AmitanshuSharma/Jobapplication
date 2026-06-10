"""Tests for src/dashboard/data_loader.py. All repository calls are mocked."""
from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.dashboard.data_loader import (
    ensure_schema,
    get_badge_counts,
    load_all_referrals,
    load_analytics_data,
    load_high_priority_jobs,
    load_inbox_jobs,
    load_jobs_by_status,
)

_CONFIG = {"database_path": "/fake/path.db", "notification_threshold": 20}

_PENDING_JOB = {
    "id": 1, "title": "Senior DE", "company": "Acme", "score": 35,
    "status": "Pending", "source_name": "greenhouse",
    "source_url": "https://example.com/1", "tags": "",
    "location_normalized": "Remote", "location": "Remote",
    "first_seen_at": "2026-06-10T10:00:00Z", "date_posted": "2026-06-08T00:00:00Z",
    "score_breakdown": None, "notified": 0, "location_ineligible": 0,
    "passed_threshold": 1, "ats_job_id": "gh-123", "dedup_hash": None,
    "description": "Build pipelines.", "experience_range": None, "tech_stack": None,
    "created_at": "2026-06-10T10:00:00Z", "updated_at": "2026-06-10T10:00:00Z",
}

_REFERRAL_NEEDED_JOB = {**_PENDING_JOB, "id": 2, "status": "Referral-Needed", "score": 25}
_APPLIED_JOB = {**_PENDING_JOB, "id": 3, "status": "Applied", "score": 30}
_REJECTED_JOB = {**_PENDING_JOB, "id": 4, "status": "Rejected", "score": 10}
_LOW_SCORE_JOB = {**_PENDING_JOB, "id": 5, "score": 5}

_REFERRAL = {
    "id": 1, "company": "Acme", "role": "DE", "referral_status": "Pending",
    "recruiter_contacted": 0, "follow_up_date": None, "applied_date": None,
    "notes": None, "job_id": None,
    "created_at": "2026-06-10T10:00:00Z", "updated_at": "2026-06-10T10:00:00Z",
}


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
def test_load_inbox_jobs_returns_dataframe(mock_status, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_status.return_value = [_PENDING_JOB]
    df = load_inbox_jobs(_CONFIG)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
def test_load_inbox_jobs_calls_correct_status(mock_status, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_status.return_value = []
    load_inbox_jobs(_CONFIG)
    mock_status.assert_called_once()
    assert mock_status.call_args[0][0] == "Pending"


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
def test_load_inbox_jobs_closes_connection(mock_status, mock_conn):
    fake_conn = MagicMock()
    mock_conn.return_value = fake_conn
    mock_status.return_value = []
    load_inbox_jobs(_CONFIG)
    fake_conn.close.assert_called_once()


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
def test_load_inbox_jobs_empty_returns_empty_dataframe(mock_status, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_status.return_value = []
    df = load_inbox_jobs(_CONFIG)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
def test_load_high_priority_excludes_below_threshold(mock_status, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_status.side_effect = [
        [_PENDING_JOB, _LOW_SCORE_JOB],  # Pending
        [_REFERRAL_NEEDED_JOB],           # Referral-Needed
    ]
    df = load_high_priority_jobs(_CONFIG)
    # _LOW_SCORE_JOB has score=5, threshold=20 — must be excluded
    assert all(df["score"] >= 20)


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
def test_load_high_priority_excludes_applied_and_rejected(mock_status, mock_conn):
    mock_conn.return_value = MagicMock()
    # load_high_priority only queries Pending and Referral-Needed
    mock_status.side_effect = [[_PENDING_JOB], [_REFERRAL_NEEDED_JOB]]
    df = load_high_priority_jobs(_CONFIG)
    if not df.empty:
        assert "Applied" not in df["status"].values
        assert "Rejected" not in df["status"].values


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
def test_load_high_priority_sorted_score_desc(mock_status, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_status.side_effect = [[_PENDING_JOB, _REFERRAL_NEEDED_JOB], []]
    df = load_high_priority_jobs(_CONFIG)
    scores = df["score"].tolist()
    assert scores == sorted(scores, reverse=True)


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.referrals_repository.get_all_referrals")
def test_load_all_referrals_returns_dataframe(mock_all, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_all.return_value = [_REFERRAL]
    df = load_all_referrals(_CONFIG)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert "company" in df.columns


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
@patch("src.dashboard.data_loader.referrals_repository.get_all_referrals")
def test_get_badge_counts_shape(mock_all_ref, mock_status, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_status.return_value = []
    mock_all_ref.return_value = []
    counts = get_badge_counts(_CONFIG)
    assert set(counts.keys()) == {"Inbox", "High Priority", "Applied", "Rejected", "Referrals"}
    assert all(isinstance(v, int) for v in counts.values())


@patch("src.dashboard.data_loader.get_connection")
@patch("src.dashboard.data_loader.jobs_repository.get_jobs_by_status")
@patch("src.dashboard.data_loader.referrals_repository.get_all_referrals")
def test_get_badge_counts_high_priority_respects_threshold(mock_all_ref, mock_status, mock_conn):
    mock_conn.return_value = MagicMock()
    # Pending has one above and one below threshold
    mock_status.side_effect = [
        [_PENDING_JOB, _LOW_SCORE_JOB],  # Pending
        [],                                # Applied
        [],                                # Referral-Needed
        [],                                # Rejected
    ]
    mock_all_ref.return_value = []
    counts = get_badge_counts(_CONFIG)
    assert counts["High Priority"] == 1  # only _PENDING_JOB passes threshold


@patch("src.dashboard.data_loader.run_migrations")
def test_ensure_schema_calls_run_migrations(mock_migrate):
    ensure_schema(_CONFIG)
    mock_migrate.assert_called_once_with(_CONFIG["database_path"])
