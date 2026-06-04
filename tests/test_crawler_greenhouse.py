# tests/test_crawler_greenhouse.py
"""Tests for src/crawlers/greenhouse.py — GreenhouseCrawler.

All HTTP calls are mocked. No database access. No network calls.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.greenhouse import GreenhouseCrawler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "greenhouse_response.json"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


_BASE_CONFIG = {
    "greenhouse_board_tokens": {"acme": "acme-token"},
    "request_timeout_seconds": 10,
    "max_retries": 1,
    "user_agent": "TestBot/1.0",
}

# ---------------------------------------------------------------------------
# parse() — unit tests (no HTTP involved)
# ---------------------------------------------------------------------------


def test_parse_returns_list_of_job_dicts_from_valid_raw():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    fixture = _load_fixture()
    raw = [dict(**job, _company_name="acme") for job in fixture["jobs"]]
    result = crawler.parse(raw)
    assert isinstance(result, list)
    assert len(result) == len(fixture["jobs"])


def test_parse_populates_required_fields():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    fixture = _load_fixture()
    first = fixture["jobs"][0]
    raw = [dict(**first, _company_name="acme")]
    result = crawler.parse(raw)
    job = result[0]
    assert job["title"] == first["title"]
    assert job["company"] == "acme"
    assert job["source_url"] == first["absolute_url"]
    assert job["ats_job_id"] == str(first["id"])
    assert job["source_name"] == "greenhouse"


def test_parse_sets_location_from_location_name():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [{
        "id": 1,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "_company_name": "acme",
        "location": {"name": "Gurugram, India"},
    }]
    result = crawler.parse(raw)
    assert result[0]["location"] == "Gurugram, India"


def test_parse_normalizes_location_with_aliases():
    config = {**_BASE_CONFIG, "location_aliases": {"gurgaon, india": "Gurugram"}}
    crawler = GreenhouseCrawler(config)
    raw = [{
        "id": 1,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "_company_name": "acme",
        "location": {"name": "Gurgaon, India"},
    }]
    result = crawler.parse(raw)
    assert result[0]["location_normalized"] == "Gurugram"


def test_parse_location_is_none_when_location_key_missing():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [{
        "id": 1,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "_company_name": "acme",
    }]
    result = crawler.parse(raw)
    assert result[0]["location"] is None
    assert result[0]["location_normalized"] is None


def test_parse_location_is_none_when_location_is_not_a_dict():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [{
        "id": 1,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "_company_name": "acme",
        "location": "not-a-dict",
    }]
    result = crawler.parse(raw)
    assert result[0]["location"] is None
    assert result[0]["location_normalized"] is None


def test_parse_skips_record_missing_title():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [
        {"id": 1, "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "_company_name": "acme"},
        {"id": 2, "title": "Data Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/2", "_company_name": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Data Engineer"


def test_parse_skips_record_missing_id():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [
        {"title": "Data Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "_company_name": "acme"},
        {"id": 2, "title": "Analytics Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/2", "_company_name": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Analytics Engineer"


def test_parse_skips_record_missing_absolute_url():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [
        {"id": 1, "title": "Data Engineer", "_company_name": "acme"},
        {"id": 2, "title": "Analytics Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/2", "_company_name": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Analytics Engineer"


def test_parse_malformed_record_does_not_fail_batch():
    """One bad record must not prevent valid records from being returned."""
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [
        {"id": 1, "title": "Data Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "_company_name": "acme"},
        {"id": 2, "absolute_url": "https://boards.greenhouse.io/acme/jobs/2", "_company_name": "acme"},  # missing title
        {"id": 3, "title": "Analytics Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/3", "_company_name": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 2
    titles = {j["title"] for j in result}
    assert "Data Engineer" in titles
    assert "Analytics Engineer" in titles


def test_parse_empty_list_returns_empty_list():
    assert GreenhouseCrawler(_BASE_CONFIG).parse([]) == []


def test_parse_raises_crawler_parse_error_for_non_list():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    with pytest.raises(CrawlerParseError):
        crawler.parse({"not": "a list"})  # type: ignore


def test_parse_ats_job_id_is_string():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [{
        "id": 4037389005,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/4037389005",
        "_company_name": "acme",
    }]
    result = crawler.parse(raw)
    assert result[0]["ats_job_id"] == "4037389005"
    assert isinstance(result[0]["ats_job_id"], str)


def test_parse_description_is_none_when_content_is_empty():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [{
        "id": 1,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "_company_name": "acme",
        "content": "",
    }]
    result = crawler.parse(raw)
    assert result[0]["description"] is None


def test_parse_description_is_none_when_content_key_is_absent():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [{
        "id": 1,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "_company_name": "acme",
    }]
    result = crawler.parse(raw)
    assert result[0]["description"] is None


def test_parse_date_posted_from_updated_at():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [{
        "id": 1,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "_company_name": "acme",
        "updated_at": "2026-05-28T10:00:00-05:00",
    }]
    result = crawler.parse(raw)
    # updated_at stored verbatim as date_posted; no UTC normalization in the crawler layer
    assert result[0]["date_posted"] == "2026-05-28T10:00:00-05:00"


def test_parse_strips_html_tags_from_content():
    """HTML content must be converted to plain text before storing as description."""
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [{
        "id": 1,
        "title": "Data Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "_company_name": "acme",
        "content": "<p>Senior Data Engineer with <strong>PySpark</strong> experience.</p>",
    }]
    result = crawler.parse(raw)
    description = result[0]["description"]
    assert "<p>" not in description
    assert "<strong>" not in description
    assert "PySpark" in description
    assert "Senior Data Engineer" in description


# ---------------------------------------------------------------------------
# fetch() tests (HTTP mocked)
# ---------------------------------------------------------------------------


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_calls_greenhouse_api_url(mock_get):
    mock_get.return_value = _mock_response({"jobs": []})
    GreenhouseCrawler({**_BASE_CONFIG, "greenhouse_board_tokens": {"acme": "acme-token"}}).fetch()
    called_url = mock_get.call_args[0][0]
    assert "boards-api.greenhouse.io/v1/boards/acme-token/jobs" in called_url


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_calls_one_url_per_board_token(mock_get):
    mock_get.return_value = _mock_response({"jobs": []})
    config = {
        "greenhouse_board_tokens": {"acme": "acme-token", "beta": "beta-token"},
        "max_retries": 1,
    }
    GreenhouseCrawler(config).fetch()
    assert mock_get.call_count == 2


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_injects_company_name_into_raw_jobs(mock_get):
    payload = {"jobs": [
        {"id": 1, "title": "Data Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/1"},
    ]}
    mock_get.return_value = _mock_response(payload)
    result = GreenhouseCrawler({**_BASE_CONFIG, "greenhouse_board_tokens": {"acme-corp": "acme-token"}}).fetch()
    assert result[0]["_company_name"] == "acme-corp"


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_skips_failed_token_continues_others(mock_get):
    """CrawlerFetchError from one token must not stop remaining tokens."""
    good_payload = {"jobs": [
        {"id": 1, "title": "Data Engineer", "absolute_url": "https://boards.greenhouse.io/beta/jobs/1"},
    ]}

    def _side_effect(url, **kwargs):
        if "acme-token" in url:
            raise CrawlerFetchError("refused")
        return _mock_response(good_payload)

    mock_get.side_effect = _side_effect
    config = {
        "greenhouse_board_tokens": {"acme": "acme-token", "beta": "beta-token"},
        "max_retries": 1,
    }
    result = GreenhouseCrawler(config).fetch()
    assert len(result) == 1


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_returns_empty_list_when_tokens_dict_is_empty(mock_get):
    result = GreenhouseCrawler({"greenhouse_board_tokens": {}}).fetch()
    assert result == []
    mock_get.assert_not_called()


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_returns_empty_list_when_tokens_key_absent(mock_get):
    result = GreenhouseCrawler({}).fetch()
    assert result == []
    mock_get.assert_not_called()


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_skips_payload_missing_jobs_key(mock_get):
    mock_get.return_value = _mock_response({"results": []})  # wrong shape
    result = GreenhouseCrawler({**_BASE_CONFIG, "greenhouse_board_tokens": {"acme": "acme-token"}}).fetch()
    assert result == []
    mock_get.assert_called_once()


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_flattens_jobs_from_multiple_tokens(mock_get):
    payload_a = {"jobs": [{"id": 1, "title": "Job A", "absolute_url": "https://boards.greenhouse.io/a/jobs/1"}]}
    payload_b = {"jobs": [
        {"id": 2, "title": "Job B", "absolute_url": "https://boards.greenhouse.io/b/jobs/2"},
        {"id": 3, "title": "Job C", "absolute_url": "https://boards.greenhouse.io/b/jobs/3"},
    ]}
    mock_get.side_effect = [_mock_response(payload_a), _mock_response(payload_b)]
    config = {"greenhouse_board_tokens": {"a": "tok-a", "b": "tok-b"}, "max_retries": 1}
    result = GreenhouseCrawler(config).fetch()
    assert len(result) == 3


# ---------------------------------------------------------------------------
# run() integration tests
# ---------------------------------------------------------------------------


@patch("src.crawlers.greenhouse.http_client.get")
def test_run_returns_job_dicts_from_fixture(mock_get):
    fixture = _load_fixture()
    mock_get.return_value = _mock_response(fixture)
    result = GreenhouseCrawler(_BASE_CONFIG).run()
    assert len(result) == len(fixture["jobs"])
    for job in result:
        assert "title" in job
        assert "company" in job
        assert "source_url" in job


@patch("src.crawlers.greenhouse.http_client.get")
def test_run_returns_empty_list_when_all_tokens_fail(mock_get):
    mock_get.side_effect = CrawlerFetchError("refused")
    result = GreenhouseCrawler(_BASE_CONFIG).run()
    assert result == []


@patch("src.crawlers.greenhouse.http_client.get")
def test_run_source_name_is_greenhouse_for_all_jobs(mock_get):
    mock_get.return_value = _mock_response(_load_fixture())
    result = GreenhouseCrawler(_BASE_CONFIG).run()
    assert len(result) > 0
    for job in result:
        assert job.get("source_name") == "greenhouse"


