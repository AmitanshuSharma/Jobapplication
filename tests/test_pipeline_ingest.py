"""Tests for src/pipeline/ingest.py — ingestion pipeline. All DB calls are mocked."""
import ast
import json
import pathlib
import sqlite3
from unittest.mock import MagicMock, patch, call

import pytest

from src.pipeline.ingest import ingest_jobs, _compute_dedup_hash


MOCK_SCORE = {
    "final_score": 30,
    "passed_threshold": True,
    "score_breakdown": {
        "role_match": True,
        "matched_positive_keywords": ["PySpark"],
        "matched_negative_keywords": [],
        "components": [{"label": "PySpark", "points": 10}],
        "final_score": 30,
        "threshold_at_ingestion": 20,
    },
}


def _make_job(**overrides):
    base = {
        "title": "Senior Data Engineer",
        "company": "Acme",
        "source_url": "https://example.com/job/1",
        "ats_job_id": "job-123",
        "location": "Remote",
        "description": "Build pipelines with PySpark.",
        "date_posted": None,
        "source_name": "greenhouse",
    }
    base.update(overrides)
    return base


def _make_config(**overrides):
    base = {
        "accepted_locations": ["Remote", "Gurugram", "Noida"],
        "location_aliases": {"gurgaon": "Gurugram"},
        "notification_threshold": 20,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_imports(path):
    tree = ast.parse(pathlib.Path(path).read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


# ---------------------------------------------------------------------------
# Basic summary tests
# ---------------------------------------------------------------------------

def test_empty_list_returns_zero_summary():
    conn = MagicMock()
    result = ingest_jobs([], _make_config(), conn)
    assert result == {
        "processed": 0,
        "inserted": 0,
        "skipped_duplicate": 0,
        "rejected": 0,
        "location_ineligible": 0,
    }


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_valid_new_job_inserted(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    result = ingest_jobs([_make_job()], _make_config(), conn)
    mock_insert.assert_called_once()
    assert result == {
        "processed": 1,
        "inserted": 1,
        "skipped_duplicate": 0,
        "rejected": 0,
        "location_ineligible": 0,
    }


# ---------------------------------------------------------------------------
# Validation / rejection tests
# ---------------------------------------------------------------------------

@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_missing_title_rejected(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    job = _make_job()
    del job["title"]
    result = ingest_jobs([job], _make_config(), conn)
    mock_insert.assert_not_called()
    assert result["rejected"] == 1
    assert result["inserted"] == 0


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_missing_company_rejected(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    job = _make_job()
    del job["company"]
    result = ingest_jobs([job], _make_config(), conn)
    mock_insert.assert_not_called()
    assert result["rejected"] == 1


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_missing_source_url_rejected(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    job = _make_job()
    del job["source_url"]
    result = ingest_jobs([job], _make_config(), conn)
    mock_insert.assert_not_called()
    assert result["rejected"] == 1


# ---------------------------------------------------------------------------
# Dedup tests
# ---------------------------------------------------------------------------

@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=True)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_duplicate_skipped(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    result = ingest_jobs([_make_job()], _make_config(), conn)
    mock_insert.assert_not_called()
    assert result["skipped_duplicate"] == 1
    assert result["inserted"] == 0


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_with_ats_job_id_dedup_hash_is_none(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    ingest_jobs([_make_job(ats_job_id="job-123")], _make_config(), conn)
    record = mock_insert.call_args[0][0]
    assert record["dedup_hash"] is None


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_without_ats_job_id_dedup_hash_computed(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    ingest_jobs([_make_job(ats_job_id=None)], _make_config(), conn)
    record = mock_insert.call_args[0][0]
    assert record["dedup_hash"] is not None
    assert len(record["dedup_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in record["dedup_hash"])


# ---------------------------------------------------------------------------
# Location eligibility tests
# ---------------------------------------------------------------------------

@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_accepted_location_eligible(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    result = ingest_jobs([_make_job(location="Remote")], _make_config(), conn)
    record = mock_insert.call_args[0][0]
    assert record["location_ineligible"] == 0
    assert result["location_ineligible"] == 0


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_unknown_location_ineligible(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    result = ingest_jobs([_make_job(location="New York")], _make_config(), conn)
    record = mock_insert.call_args[0][0]
    assert record["location_ineligible"] == 1
    assert result["location_ineligible"] == 1


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_none_location_ineligible(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    result = ingest_jobs([_make_job(location=None)], _make_config(), conn)
    record = mock_insert.call_args[0][0]
    assert record["location_ineligible"] == 1
    assert result["location_ineligible"] == 1


# ---------------------------------------------------------------------------
# Score field tests
# ---------------------------------------------------------------------------

@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_score_stored_in_record(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    ingest_jobs([_make_job()], _make_config(), conn)
    record = mock_insert.call_args[0][0]
    assert record["score"] == MOCK_SCORE["final_score"]


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_score_breakdown_json_encoded(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    ingest_jobs([_make_job()], _make_config(), conn)
    record = mock_insert.call_args[0][0]
    # Must not raise
    parsed = json.loads(record["score_breakdown"])
    assert isinstance(parsed, dict)


@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_passed_threshold_stored_as_int(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    ingest_jobs([_make_job()], _make_config(), conn)
    record = mock_insert.call_args[0][0]
    assert record["passed_threshold"] in (0, 1)
    assert not isinstance(record["passed_threshold"], bool)


# ---------------------------------------------------------------------------
# Batch / mixed results test
# ---------------------------------------------------------------------------

@patch("src.pipeline.ingest.job_exists_by_dedup_key")
@patch("src.pipeline.ingest.insert_job", return_value=1)
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_batch_mixed_results(mock_score, mock_insert, mock_exists):
    conn = MagicMock()

    # job1: missing title → rejected
    job1 = _make_job()
    del job1["title"]

    # job2: duplicate
    job2 = _make_job(source_url="https://example.com/job/2", ats_job_id="job-456")

    # job3: valid but unknown location → inserted, location_ineligible
    job3 = _make_job(
        source_url="https://example.com/job/3",
        ats_job_id="job-789",
        location="New York",
    )

    # job_exists returns False for job1 (won't reach dedup), True for job2, False for job3
    def _exists_side_effect(source_url, ats_job_id, dedup_hash, conn):
        if source_url == "https://example.com/job/2":
            return True
        return False

    mock_exists.side_effect = _exists_side_effect

    result = ingest_jobs([job1, job2, job3], _make_config(), conn)
    assert result == {
        "processed": 3,
        "inserted": 1,
        "skipped_duplicate": 1,
        "rejected": 1,
        "location_ineligible": 1,
    }


# ---------------------------------------------------------------------------
# Exception propagation test
# ---------------------------------------------------------------------------

@patch("src.pipeline.ingest.job_exists_by_dedup_key", return_value=False)
@patch("src.pipeline.ingest.insert_job", side_effect=RuntimeError("db failure"))
@patch("src.pipeline.ingest.score_job", return_value=MOCK_SCORE)
def test_exception_propagates_without_swallowing(mock_score, mock_insert, mock_exists):
    conn = MagicMock()
    with pytest.raises(RuntimeError, match="db failure"):
        ingest_jobs([_make_job()], _make_config(), conn)
    # ingest must never call conn.close()
    conn.close.assert_not_called()


# ---------------------------------------------------------------------------
# Boundary / import isolation tests
# ---------------------------------------------------------------------------

def test_boundary_scorer_no_db_import():
    imports = _get_imports("src/scoring/scorer.py")
    assert not any("db" in m or "sqlite3" in m for m in imports)


def test_boundary_repository_no_scoring_import():
    imports = _get_imports("src/db/jobs_repository.py")
    assert not any("scoring" in m for m in imports)


def test_boundary_ingest_no_notifications_import():
    imports = _get_imports("src/pipeline/ingest.py")
    assert not any("notifications" in m or "crawlers" in m or "streamlit" in m for m in imports)


# ---------------------------------------------------------------------------
# Integration test — real SQLite DB, no mocks
# ---------------------------------------------------------------------------

def test_integration_valid_job_inserted_to_real_db():
    """Insert a real record and read it back to verify the field contract."""
    from src.db.connection import get_connection
    from src.db.migrations import run_migrations
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        run_migrations(db_path)
        conn = get_connection(db_path)
        job = _make_job()
        config = _make_config(
            positive_keywords={"PySpark": 10},
            negative_keywords={},
            accepted_role_keywords=["Data Engineer"],
            notification_threshold=20,
            remote_location_bonus=5,
            company_tier_1=[],
            company_tier_2=[],
            role_mismatch_penalty=-50,
            company_tier_1_bonus=8,
            company_tier_2_bonus=5,
        )
        summary = ingest_jobs([job], config, conn)
        assert summary["inserted"] == 1

        row = conn.execute("SELECT * FROM jobs WHERE source_url = ?", (job["source_url"],)).fetchone()
        assert row is not None
        assert row["title"] == job["title"]
        assert row["company"] == job["company"]
        assert row["score"] is not None
        assert row["status"] == "Pending"
        assert row["notified"] == 0
        assert row["location_ineligible"] == 0
        conn.close()
    finally:
        os.unlink(db_path)
