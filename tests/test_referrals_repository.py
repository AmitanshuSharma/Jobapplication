"""Tests for src/db/referrals_repository.py. All tests use tmp_path — no production DB."""
import pytest

from src.db.connection import get_connection
from src.db.migrations import run_migrations
from src.db.referrals_repository import (
    insert_referral,
    get_referral_by_id,
    get_all_referrals,
    update_referral_status,
)


@pytest.fixture
def conn(tmp_path):
    """Migrated database connection. Caller owns the lifecycle."""
    db_path = str(tmp_path / "test.db")
    run_migrations(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


def _make_referral(**overrides):
    """Return a minimal valid referral record dict."""
    base = {
        "company": "Acme",
        "role": "Data Engineer",
        "applied_date": None,
        "referral_status": "Pending",
        "recruiter_contacted": 0,
        "follow_up_date": None,
        "notes": None,
        "job_id": None,
    }
    base.update(overrides)
    return base


# --- insert_referral ---

def test_insert_referral_returns_integer_id(conn):
    ref_id = insert_referral(_make_referral(), conn)
    assert isinstance(ref_id, int)
    assert ref_id > 0


def test_insert_referral_stores_fields(conn):
    insert_referral(_make_referral(company="Globex", role="DE Lead"), conn)
    row = get_referral_by_id(1, conn)
    assert row["company"] == "Globex"
    assert row["role"] == "DE Lead"
    assert row["recruiter_contacted"] == 0


def test_insert_referral_sets_utc_z_timestamps(conn):
    insert_referral(_make_referral(), conn)
    row = get_referral_by_id(1, conn)
    assert row["created_at"].endswith("Z")
    assert row["updated_at"].endswith("Z")
    assert row["created_at"] == row["updated_at"]


# --- get_referral_by_id ---

def test_get_referral_by_id_returns_dict(conn):
    ref_id = insert_referral(_make_referral(), conn)
    row = get_referral_by_id(ref_id, conn)
    assert isinstance(row, dict)
    assert row["id"] == ref_id


def test_get_referral_by_id_not_found_returns_none(conn):
    assert get_referral_by_id(9999, conn) is None


# --- get_all_referrals ---

def test_get_all_referrals_returns_all_rows(conn):
    insert_referral(_make_referral(company="A"), conn)
    insert_referral(_make_referral(company="B"), conn)
    assert len(get_all_referrals(conn)) == 2


def test_get_all_referrals_empty_returns_empty_list(conn):
    assert get_all_referrals(conn) == []


def test_get_all_referrals_nulls_last_for_follow_up_date(conn):
    # A row with follow_up_date must sort before rows with NULL follow_up_date.
    insert_referral(_make_referral(company="NoDate", follow_up_date=None), conn)
    insert_referral(_make_referral(company="HasDate", follow_up_date="2026-06-01"), conn)
    rows = get_all_referrals(conn)
    assert rows[0]["company"] == "HasDate"
    assert rows[1]["company"] == "NoDate"


# --- update_referral_status ---

def test_update_referral_status_changes_status_and_follow_up(conn):
    ref_id = insert_referral(_make_referral(referral_status="Pending"), conn)
    update_referral_status(ref_id, "Confirmed", "2026-07-01", conn)
    row = get_referral_by_id(ref_id, conn)
    assert row["referral_status"] == "Confirmed"
    assert row["follow_up_date"] == "2026-07-01"


def test_update_referral_status_sets_utc_z_updated_at(conn):
    ref_id = insert_referral(_make_referral(), conn)
    update_referral_status(ref_id, "Confirmed", None, conn)
    assert get_referral_by_id(ref_id, conn)["updated_at"].endswith("Z")


def test_update_referral_status_does_not_affect_company(conn):
    ref_id = insert_referral(_make_referral(company="Acme"), conn)
    update_referral_status(ref_id, "Declined", None, conn)
    assert get_referral_by_id(ref_id, conn)["company"] == "Acme"
