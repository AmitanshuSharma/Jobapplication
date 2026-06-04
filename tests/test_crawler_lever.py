# tests/test_crawler_lever.py
"""Tests for src/crawlers/lever.py — LeverCrawler.

All HTTP calls are mocked. No database access. No network calls.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.lever import LeverCrawler

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lever_response.json"


def _load_fixture() -> list:
    return json.loads(_FIXTURE_PATH.read_text())


def _mock_response(payload) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


_BASE_CONFIG = {
    "lever_company_ids": ["acme"],
    "request_timeout_seconds": 10,
    "max_retries": 1,
    "user_agent": "TestBot/1.0",
}


# ---------------------------------------------------------------------------
# parse() — unit tests (no HTTP involved)
# ---------------------------------------------------------------------------


def test_parse_returns_list_of_job_dicts_from_valid_raw():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [dict(**job, _company_id="acme") for job in _load_fixture()]
    result = crawler.parse(raw)
    assert isinstance(result, list)
    assert len(result) == len(_load_fixture())


def test_parse_populates_required_fields():
    crawler = LeverCrawler(_BASE_CONFIG)
    first = _load_fixture()[0]
    raw = [dict(**first, _company_id="acme")]
    result = crawler.parse(raw)
    job = result[0]
    assert job["title"] == first["text"]
    assert job["company"] == "acme"
    assert job["source_url"] == first["hostedUrl"]
    assert job["ats_job_id"] == first["id"]
    assert job["source_name"] == "lever"


def test_parse_sets_location_from_categories():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
        "categories": {"location": "Gurugram, India"},
    }]
    result = crawler.parse(raw)
    assert result[0]["location"] == "Gurugram, India"


def test_parse_normalizes_location_with_aliases():
    config = {**_BASE_CONFIG, "location_aliases": {"gurgaon, india": "Gurugram"}}
    crawler = LeverCrawler(config)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
        "categories": {"location": "Gurgaon, India"},
    }]
    result = crawler.parse(raw)
    assert result[0]["location_normalized"] == "Gurugram"


def test_parse_location_is_none_when_categories_key_missing():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
    }]
    result = crawler.parse(raw)
    assert result[0]["location"] is None
    assert result[0]["location_normalized"] is None


def test_parse_location_is_none_when_categories_is_not_a_dict():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
        "categories": "not-a-dict",
    }]
    result = crawler.parse(raw)
    assert result[0]["location"] is None
    assert result[0]["location_normalized"] is None


def test_parse_skips_record_missing_text():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [
        {"id": "uuid-001", "hostedUrl": "https://jobs.lever.co/acme/uuid-001", "_company_id": "acme"},
        {"id": "uuid-002", "text": "Data Engineer", "hostedUrl": "https://jobs.lever.co/acme/uuid-002", "_company_id": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Data Engineer"


def test_parse_skips_record_missing_id():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [
        {"text": "Data Engineer", "hostedUrl": "https://jobs.lever.co/acme/uuid-001", "_company_id": "acme"},
        {"id": "uuid-002", "text": "Analytics Engineer", "hostedUrl": "https://jobs.lever.co/acme/uuid-002", "_company_id": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Analytics Engineer"


def test_parse_skips_record_missing_hosted_url():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [
        {"id": "uuid-001", "text": "Data Engineer", "_company_id": "acme"},
        {"id": "uuid-002", "text": "Analytics Engineer", "hostedUrl": "https://jobs.lever.co/acme/uuid-002", "_company_id": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Analytics Engineer"


def test_parse_malformed_record_does_not_fail_batch():
    """One bad record must not prevent valid records from being returned."""
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [
        {"id": "uuid-001", "text": "Data Engineer", "hostedUrl": "https://jobs.lever.co/acme/uuid-001", "_company_id": "acme"},
        {"id": "uuid-002", "hostedUrl": "https://jobs.lever.co/acme/uuid-002", "_company_id": "acme"},  # missing text
        {"id": "uuid-003", "text": "Analytics Engineer", "hostedUrl": "https://jobs.lever.co/acme/uuid-003", "_company_id": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 2
    titles = {j["title"] for j in result}
    assert "Data Engineer" in titles
    assert "Analytics Engineer" in titles


def test_parse_empty_list_returns_empty_list():
    assert LeverCrawler(_BASE_CONFIG).parse([]) == []


def test_parse_raises_crawler_parse_error_for_non_list():
    crawler = LeverCrawler(_BASE_CONFIG)
    with pytest.raises(CrawlerParseError):
        crawler.parse({"not": "a list"})  # type: ignore


def test_parse_ats_job_id_is_string():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "a1b2c3d4-0001-0001-0001-000000000001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/a1b2c3d4-0001-0001-0001-000000000001",
        "_company_id": "acme",
    }]
    result = crawler.parse(raw)
    assert result[0]["ats_job_id"] == "a1b2c3d4-0001-0001-0001-000000000001"
    assert isinstance(result[0]["ats_job_id"], str)


def test_parse_description_is_none_when_content_is_absent():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
    }]
    result = crawler.parse(raw)
    assert result[0]["description"] is None


def test_parse_description_is_none_when_both_html_and_plain_are_empty():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
        "content": {"descriptionHtml": "", "description": ""},
    }]
    result = crawler.parse(raw)
    assert result[0]["description"] is None


def test_parse_strips_html_tags_from_description_html():
    """HTML content must be converted to plain text before storing as description."""
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
        "content": {
            "descriptionHtml": "<p>Senior Data Engineer with <strong>PySpark</strong> experience.</p>",
        },
    }]
    result = crawler.parse(raw)
    description = result[0]["description"]
    assert "<p>" not in description
    assert "<strong>" not in description
    assert "PySpark" in description
    assert "Senior Data Engineer" in description


def test_parse_falls_back_to_plain_description_when_html_is_absent():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
        "content": {"description": "Plain text description."},
    }]
    result = crawler.parse(raw)
    assert result[0]["description"] == "Plain text description."


def test_parse_date_posted_from_created_at_ms():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
        "createdAt": 1748476800000,  # 2025-05-29T00:00:00Z
    }]
    result = crawler.parse(raw)
    assert result[0]["date_posted"] == "2025-05-29T00:00:00Z"


def test_parse_date_posted_is_none_when_created_at_absent():
    crawler = LeverCrawler(_BASE_CONFIG)
    raw = [{
        "id": "uuid-001",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/uuid-001",
        "_company_id": "acme",
    }]
    result = crawler.parse(raw)
    assert result[0]["date_posted"] is None


# ---------------------------------------------------------------------------
# fetch() — tests (HTTP mocked)
# ---------------------------------------------------------------------------


@patch("src.crawlers.lever.http_client.get")
def test_fetch_calls_lever_api_url(mock_get):
    mock_get.return_value = _mock_response([])
    LeverCrawler({**_BASE_CONFIG, "lever_company_ids": ["acme"]}).fetch()
    called_url = mock_get.call_args[0][0]
    assert "api.lever.co/v0/postings/acme" in called_url


@patch("src.crawlers.lever.http_client.get")
def test_fetch_calls_one_url_per_company_id(mock_get):
    mock_get.return_value = _mock_response([])
    config = {**_BASE_CONFIG, "lever_company_ids": ["acme", "beta"]}
    LeverCrawler(config).fetch()
    assert mock_get.call_count == 2


@patch("src.crawlers.lever.http_client.get")
def test_fetch_injects_company_id_into_raw_jobs(mock_get):
    payload = [
        {"id": "uuid-001", "text": "Data Engineer", "hostedUrl": "https://jobs.lever.co/acme/uuid-001"},
    ]
    mock_get.return_value = _mock_response(payload)
    result = LeverCrawler({**_BASE_CONFIG, "lever_company_ids": ["acme-corp"]}).fetch()
    assert result[0]["_company_id"] == "acme-corp"


@patch("src.crawlers.lever.http_client.get")
def test_fetch_skips_failed_company_continues_others(mock_get):
    """CrawlerFetchError from one company must not stop remaining companies."""
    good_payload = [
        {"id": "uuid-001", "text": "Data Engineer", "hostedUrl": "https://jobs.lever.co/beta/uuid-001"},
    ]

    def _side_effect(url, **kwargs):
        if "acme" in url:
            raise CrawlerFetchError("refused")
        return _mock_response(good_payload)

    mock_get.side_effect = _side_effect
    config = {**_BASE_CONFIG, "lever_company_ids": ["acme", "beta"]}
    result = LeverCrawler(config).fetch()
    assert len(result) == 1


@patch("src.crawlers.lever.http_client.get")
def test_fetch_returns_empty_list_when_company_ids_is_empty(mock_get):
    result = LeverCrawler({"lever_company_ids": []}).fetch()
    assert result == []
    mock_get.assert_not_called()


@patch("src.crawlers.lever.http_client.get")
def test_fetch_returns_empty_list_when_company_ids_key_absent(mock_get):
    result = LeverCrawler({}).fetch()
    assert result == []
    mock_get.assert_not_called()


@patch("src.crawlers.lever.http_client.get")
def test_fetch_skips_non_array_payload(mock_get):
    """Lever must return a JSON array; a dict payload is rejected."""
    mock_get.return_value = _mock_response({"jobs": []})  # wrong shape
    result = LeverCrawler({**_BASE_CONFIG, "lever_company_ids": ["acme"]}).fetch()
    assert result == []
    mock_get.assert_called_once()


@patch("src.crawlers.lever.http_client.get")
def test_fetch_flattens_jobs_from_multiple_companies(mock_get):
    payload_a = [{"id": "u1", "text": "Job A", "hostedUrl": "https://jobs.lever.co/a/u1"}]
    payload_b = [
        {"id": "u2", "text": "Job B", "hostedUrl": "https://jobs.lever.co/b/u2"},
        {"id": "u3", "text": "Job C", "hostedUrl": "https://jobs.lever.co/b/u3"},
    ]
    mock_get.side_effect = [_mock_response(payload_a), _mock_response(payload_b)]
    config = {**_BASE_CONFIG, "lever_company_ids": ["a", "b"]}
    result = LeverCrawler(config).fetch()
    assert len(result) == 3


# ---------------------------------------------------------------------------
# run() — integration tests
# ---------------------------------------------------------------------------


@patch("src.crawlers.lever.http_client.get")
def test_run_returns_job_dicts_from_fixture(mock_get):
    fixture = _load_fixture()
    mock_get.return_value = _mock_response(fixture)
    result = LeverCrawler(_BASE_CONFIG).run()
    assert len(result) == len(fixture)
    for job in result:
        assert "title" in job
        assert "company" in job
        assert "source_url" in job


@patch("src.crawlers.lever.http_client.get")
def test_run_returns_empty_list_when_all_companies_fail(mock_get):
    mock_get.side_effect = CrawlerFetchError("refused")
    result = LeverCrawler(_BASE_CONFIG).run()
    assert result == []


@patch("src.crawlers.lever.http_client.get")
def test_run_source_name_is_lever_for_all_jobs(mock_get):
    mock_get.return_value = _mock_response(_load_fixture())
    result = LeverCrawler(_BASE_CONFIG).run()
    assert len(result) > 0
    for job in result:
        assert job.get("source_name") == "lever"
