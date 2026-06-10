"""Tests for src/scheduler/runner.py.

All crawlers, ingest_jobs, dispatch_new_jobs, and get_connection are mocked.
No real DB, no real HTTP.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.scheduler.runner import run_pipeline


CONFIG = {
    "database_path": "/fake/jobs.db",
    "notification_threshold": 20,
}


def _zero_ingest():
    return {
        "processed": 0,
        "inserted": 0,
        "skipped_duplicate": 0,
        "rejected": 0,
        "location_ineligible": 0,
    }


def _zero_dispatch():
    return {"eligible": 0, "attempted": 0, "notified": 0, "both_failed": 0}


@pytest.fixture
def mocks():
    """Patch all external dependencies of run_pipeline."""
    mock_conn = MagicMock()
    with patch("src.scheduler.runner.get_connection", return_value=mock_conn), \
         patch("src.scheduler.runner.GreenhouseCrawler") as MockGH, \
         patch("src.scheduler.runner.LeverCrawler") as MockLV, \
         patch("src.scheduler.runner.WorkdayCrawler") as MockWD, \
         patch("src.scheduler.runner.ingest_jobs", return_value=_zero_ingest()) as mock_ingest, \
         patch("src.scheduler.runner.dispatch_new_jobs", return_value=_zero_dispatch()) as mock_dispatch:
        MockGH.return_value.run.return_value = []
        MockLV.return_value.run.return_value = []
        MockWD.return_value.run.return_value = []
        yield {
            "conn": mock_conn,
            "GH": MockGH,
            "LV": MockLV,
            "WD": MockWD,
            "ingest": mock_ingest,
            "dispatch": mock_dispatch,
        }


# ---------------------------------------------------------------------------
# Summary shape
# ---------------------------------------------------------------------------

def test_summary_has_all_keys(mocks):
    result = run_pipeline(CONFIG)
    assert set(result.keys()) == {
        "greenhouse_jobs", "lever_jobs", "workday_jobs",
        "inserted_jobs", "duplicate_jobs", "rejected_jobs",
        "notifications_sent", "notification_failures", "dispatch_failed",
    }


def test_dispatch_failed_false_on_success(mocks):
    result = run_pipeline(CONFIG)
    assert result["dispatch_failed"] is False


# ---------------------------------------------------------------------------
# Happy path counts
# ---------------------------------------------------------------------------

def test_happy_path_counts(mocks):
    mocks["GH"].return_value.run.return_value = [{"title": "GH1"}, {"title": "GH2"}]
    mocks["LV"].return_value.run.return_value = [{"title": "LV1"}]
    mocks["WD"].return_value.run.return_value = []

    mocks["ingest"].side_effect = [
        {"processed": 2, "inserted": 2, "skipped_duplicate": 0, "rejected": 0, "location_ineligible": 0},
        {"processed": 1, "inserted": 0, "skipped_duplicate": 1, "rejected": 0, "location_ineligible": 0},
        _zero_ingest(),
    ]
    mocks["dispatch"].return_value = {
        "eligible": 2, "attempted": 2, "notified": 2, "both_failed": 0,
    }

    result = run_pipeline(CONFIG)

    assert result["greenhouse_jobs"] == 2
    assert result["lever_jobs"] == 1
    assert result["workday_jobs"] == 0
    assert result["inserted_jobs"] == 2
    assert result["duplicate_jobs"] == 1
    assert result["rejected_jobs"] == 0
    assert result["notifications_sent"] == 2
    assert result["notification_failures"] == 0
    assert result["dispatch_failed"] is False


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------

def test_greenhouse_failure_others_continue(mocks):
    mocks["GH"].side_effect = RuntimeError("greenhouse config missing")
    mocks["LV"].return_value.run.return_value = [{"title": "LV1"}]
    mocks["WD"].return_value.run.return_value = [{"title": "WD1"}]

    result = run_pipeline(CONFIG)

    assert result["greenhouse_jobs"] == 0
    assert result["lever_jobs"] == 1
    assert result["workday_jobs"] == 1
    assert mocks["ingest"].call_count == 2


def test_ingest_failure_others_continue(mocks):
    mocks["GH"].return_value.run.return_value = [{"title": "GH1"}]
    mocks["LV"].return_value.run.return_value = [{"title": "LV1"}]
    mocks["WD"].return_value.run.return_value = [{"title": "WD1"}]

    mocks["ingest"].side_effect = [
        RuntimeError("DB write failed"),
        _zero_ingest(),
        _zero_ingest(),
    ]

    result = run_pipeline(CONFIG)

    assert mocks["ingest"].call_count == 3
    assert result["dispatch_failed"] is False


def test_dispatch_failure_returns_summary(mocks):
    mocks["dispatch"].side_effect = RuntimeError("Telegram timeout")

    result = run_pipeline(CONFIG)

    assert result["dispatch_failed"] is True
    assert result["notifications_sent"] == 0
    assert result["notification_failures"] == 0


# ---------------------------------------------------------------------------
# Dispatch called once, after all ingestion
# ---------------------------------------------------------------------------

def test_dispatch_called_once_after_all_ingestion(mocks):
    mocks["GH"].return_value.run.return_value = [{"title": "GH1"}]
    mocks["LV"].return_value.run.return_value = [{"title": "LV1"}]
    mocks["WD"].return_value.run.return_value = [{"title": "WD1"}]

    run_pipeline(CONFIG)

    assert mocks["dispatch"].call_count == 1
    assert mocks["ingest"].call_count == 3


# ---------------------------------------------------------------------------
# Execution order
# ---------------------------------------------------------------------------

def test_execution_order():
    """Verifies: GH.run → ingest → LV.run → ingest → WD.run → ingest → dispatch."""
    call_log = []
    mock_conn = MagicMock()

    gh_jobs = [{"title": "GH"}]
    lv_jobs = [{"title": "LV"}]
    wd_jobs = [{"title": "WD"}]

    def _track_ingest(jobs, config, conn):
        if jobs and jobs[0]["title"] == "GH":
            call_log.append("ingest_greenhouse")
        elif jobs and jobs[0]["title"] == "LV":
            call_log.append("ingest_lever")
        elif jobs and jobs[0]["title"] == "WD":
            call_log.append("ingest_workday")
        return _zero_ingest()

    def _track_dispatch(config, conn):
        call_log.append("dispatch")
        return _zero_dispatch()

    with patch("src.scheduler.runner.get_connection", return_value=mock_conn), \
         patch("src.scheduler.runner.GreenhouseCrawler") as MockGH, \
         patch("src.scheduler.runner.LeverCrawler") as MockLV, \
         patch("src.scheduler.runner.WorkdayCrawler") as MockWD, \
         patch("src.scheduler.runner.ingest_jobs", side_effect=_track_ingest), \
         patch("src.scheduler.runner.dispatch_new_jobs", side_effect=_track_dispatch):

        def _gh_run():
            call_log.append("greenhouse_run")
            return gh_jobs

        def _lv_run():
            call_log.append("lever_run")
            return lv_jobs

        def _wd_run():
            call_log.append("workday_run")
            return wd_jobs

        MockGH.return_value.run.side_effect = _gh_run
        MockLV.return_value.run.side_effect = _lv_run
        MockWD.return_value.run.side_effect = _wd_run

        run_pipeline(CONFIG)

    assert call_log == [
        "greenhouse_run",
        "ingest_greenhouse",
        "lever_run",
        "ingest_lever",
        "workday_run",
        "ingest_workday",
        "dispatch",
    ]


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------

def test_connection_closed_on_success(mocks):
    run_pipeline(CONFIG)
    mocks["conn"].close.assert_called_once()


def test_connection_closed_on_crawler_failure(mocks):
    mocks["GH"].side_effect = RuntimeError("boom")
    mocks["LV"].side_effect = RuntimeError("boom")
    mocks["WD"].side_effect = RuntimeError("boom")
    run_pipeline(CONFIG)
    mocks["conn"].close.assert_called_once()


def test_connection_closed_on_dispatch_failure(mocks):
    mocks["dispatch"].side_effect = RuntimeError("dispatch exploded")
    run_pipeline(CONFIG)
    mocks["conn"].close.assert_called_once()


# ---------------------------------------------------------------------------
# Notification summary fields
# ---------------------------------------------------------------------------

def test_notification_counts_from_dispatch(mocks):
    mocks["dispatch"].return_value = {
        "eligible": 5, "attempted": 5, "notified": 4, "both_failed": 1,
    }
    result = run_pipeline(CONFIG)
    assert result["notifications_sent"] == 4
    assert result["notification_failures"] == 1
