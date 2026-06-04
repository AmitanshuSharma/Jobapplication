# Lever Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `LeverCrawler` that fetches open roles from the Lever public postings API, parses them into `JobDict` objects with location normalization and HTML stripping — with no database, scoring, or notification access.

**Architecture:** `LeverCrawler` extends `BaseCrawler`, uses `http_client.get()` to call `https://api.lever.co/v0/postings/{company}?mode=json` for each configured company slug in `lever_company_ids` (list). Injects `_company_id` into each raw dict so `parse()` can set the `company` field. Per-record isolation (Model B) ensures one malformed record cannot fail the batch. `CrawlerParseError` is reserved for structural failures only.

**Tech Stack:** Python 3.11+, `requests` (via `http_client`), `BeautifulSoup` (HTML stripping), `pytest` + `unittest.mock` for tests.

---

## File Map

| Action | Path |
|---|---|
| Create | `src/crawlers/lever.py` |
| Create | `tests/fixtures/lever_response.json` |
| Create | `tests/test_crawler_lever.py` |

---

## Lever API Payload Shape

`GET https://api.lever.co/v0/postings/{company}?mode=json` returns a **flat JSON array** (not a nested object like Greenhouse).

```json
[
  {
    "id": "a1b2c3d4-0001-0001-0001-000000000001",
    "text": "Senior Data Engineer",
    "hostedUrl": "https://jobs.lever.co/acme/a1b2c3d4-0001-0001-0001-000000000001",
    "applyUrl": "https://jobs.lever.co/acme/a1b2c3d4-0001-0001-0001-000000000001/apply",
    "createdAt": 1748476800000,
    "categories": {
      "location": "Gurugram, India",
      "team": "Data Engineering",
      "department": "Engineering",
      "commitment": "Full-time"
    },
    "content": {
      "description": "Senior Data Engineer with PySpark experience.",
      "descriptionHtml": "<p>Senior Data Engineer with <strong>PySpark</strong> experience.</p>",
      "body": "<div>...</div>",
      "lists": []
    },
    "tags": ["data", "engineering"]
  }
]
```

**Key differences from Greenhouse:**

| Field | Greenhouse | Lever |
|---|---|---|
| API returns | `{"jobs": [...]}` (object) | `[...]` (flat array) |
| Title | `title` | `text` |
| Job URL | `absolute_url` | `hostedUrl` |
| Job ID | integer | UUID string |
| Location | `location.name` (nested dict) | `categories.location` (nested dict) |
| Date | `updated_at` (ISO string) | `createdAt` (milliseconds since epoch) |
| Description | `content` (HTML) | `content.descriptionHtml` (HTML) |
| Company inject key | `_company_name` | `_company_id` |
| Config key | `greenhouse_board_tokens` (dict) | `lever_company_ids` (list of slugs) |

---

## Task 1: Create the Lever fixture file

**Files:**
- Create: `tests/fixtures/lever_response.json`

- [ ] **Step 1: Create the fixture JSON**

`1748476800000` ms = `2025-05-29T00:00:00Z` (UTC); `1748390400000` ms = `2025-05-28T00:00:00Z` (UTC).

File: `tests/fixtures/lever_response.json`

```json
[
  {
    "id": "a1b2c3d4-0001-0001-0001-000000000001",
    "text": "Senior Data Engineer",
    "hostedUrl": "https://jobs.lever.co/acme/a1b2c3d4-0001-0001-0001-000000000001",
    "applyUrl": "https://jobs.lever.co/acme/a1b2c3d4-0001-0001-0001-000000000001/apply",
    "createdAt": 1748476800000,
    "categories": {
      "location": "Gurugram, India",
      "team": "Data Engineering",
      "department": "Engineering",
      "commitment": "Full-time"
    },
    "content": {
      "description": "Senior Data Engineer with PySpark and Databricks experience. 5+ years required.",
      "descriptionHtml": "<p>Senior Data Engineer with <strong>PySpark</strong> and <em>Databricks</em> experience.</p><ul><li>5+ years required</li></ul>",
      "body": "<div><p>Senior Data Engineer with PySpark and Databricks experience.</p></div>",
      "lists": []
    },
    "tags": ["data", "engineering"]
  },
  {
    "id": "a1b2c3d4-0002-0002-0002-000000000002",
    "text": "Analytics Engineer",
    "hostedUrl": "https://jobs.lever.co/acme/a1b2c3d4-0002-0002-0002-000000000002",
    "applyUrl": "https://jobs.lever.co/acme/a1b2c3d4-0002-0002-0002-000000000002/apply",
    "createdAt": 1748390400000,
    "categories": {
      "location": "Remote",
      "team": "Analytics",
      "department": "Engineering",
      "commitment": "Full-time"
    },
    "content": {
      "description": "Analytics Engineer with dbt and Snowflake.",
      "descriptionHtml": "<p>Analytics Engineer with dbt and Snowflake.</p>",
      "body": "<p>Analytics Engineer with dbt and Snowflake.</p>",
      "lists": []
    },
    "tags": ["analytics"]
  }
]
```

- [ ] **Step 2: Verify file exists**

```bash
ls tests/fixtures/lever_response.json
```
Expected: file listed.

---

## Task 2: parse() — write failing tests, implement, pass

**Files:**
- Create: `tests/test_crawler_lever.py`
- Create: `src/crawlers/lever.py`

- [ ] **Step 3: Write failing parse() tests**

Create `tests/test_crawler_lever.py`:

```python
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
```

- [ ] **Step 4: Run parse() tests to confirm they fail (module not yet created)**

```bash
pytest tests/test_crawler_lever.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError` or `ImportError` for `src.crawlers.lever`.

- [ ] **Step 5: Create `src/crawlers/lever.py`**

```python
# src/crawlers/lever.py
"""Lever public postings API crawler.

Inputs:  config dict — lever_company_ids (list), request settings, location_aliases.
Outputs: list[JobDict] from run() — one entry per valid open role found.
No database access. No scoring. No notifications. No Playwright.
"""
from __future__ import annotations

import datetime
import logging

from bs4 import BeautifulSoup

from src.crawlers import http_client
from src.crawlers.base import BaseCrawler
from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.models import JobDict
from src.utils.normalizer import normalize_location

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.lever.co/v0/postings/{company}?mode=json"


class LeverCrawler(BaseCrawler):
    """Fetches open roles from the Lever public postings API.

    Config keys:
        lever_company_ids (list): Company slug identifier strings.
        request_timeout_seconds (int): HTTP timeout in seconds. Default 30.
        max_retries (int): Retry attempts per URL. Default 3.
        user_agent (str): User-Agent header value.
        location_aliases (dict): Passed to normalize_location(). Optional.
    """

    def fetch(self) -> list[dict]:
        """Fetch raw job dicts from all configured Lever company slugs.

        Calls the Lever postings API for each company slug. Injects '_company_id'
        into each raw job dict so parse() can set the company field.
        A CrawlerFetchError for one slug is logged and skipped; others continue.
        JSON decode errors and non-array payloads are also logged and skipped per-slug.

        Returns:
            Flat list of raw job dicts from all successful API responses.
        """
        company_ids: list[str] = self.config.get("lever_company_ids") or []
        if not company_ids:
            logger.warning("LeverCrawler: no company IDs configured — skipping fetch")
            return []

        raw_jobs: list[dict] = []
        for company_id in company_ids:
            url = _BASE_URL.format(company=company_id)
            try:
                response = http_client.get(
                    url,
                    headers={"User-Agent": self.config.get("user_agent", "JobIntelligencePlatform/1.0")},
                    timeout=self.config.get("request_timeout_seconds", 30),
                    max_retries=self.config.get("max_retries", 3),
                )
            except CrawlerFetchError as exc:
                logger.error("LeverCrawler: fetch failed for %s — %s", company_id, exc)
                continue

            try:
                payload = response.json()
            except Exception as exc:
                logger.error("LeverCrawler: invalid JSON from %s — %s", url, exc)
                continue

            # Lever returns a flat JSON array, not a nested dict
            if not isinstance(payload, list):
                logger.error(
                    "LeverCrawler: expected JSON array from %s, got %s", url, type(payload).__name__
                )
                continue

            for job in payload:
                job["_company_id"] = company_id
                raw_jobs.append(job)

        return raw_jobs

    def parse(self, raw: list[dict]) -> list[JobDict]:
        """Parse a flat list of raw Lever job dicts into JobDict objects.

        Model B: skips malformed records (logs reason only), returns valid ones.
        Raises CrawlerParseError only if raw is not a list (structural failure).

        Args:
            raw: List of raw job dicts as returned by fetch().

        Returns:
            List of valid JobDict objects.

        Raises:
            CrawlerParseError: If raw is not a list.
        """
        if not isinstance(raw, list):
            raise CrawlerParseError(
                f"LeverCrawler: expected list from fetch(), got {type(raw).__name__}"
            )

        results: list[JobDict] = []
        for item in raw:
            job = self._parse_one(item)
            if job is not None:
                results.append(job)
        return results

    def _parse_one(self, item: dict) -> JobDict | None:
        """Validate and map a single raw Lever job dict to a JobDict.

        Required fields: text, id, hostedUrl, _company_id.
        Returns None (and logs the reason) if any required field is absent.
        categories, content, and createdAt are optional and may be absent.

        Args:
            item: Single raw job dict from the Lever postings API.

        Returns:
            Populated JobDict on success, None on validation failure.
        """
        if not isinstance(item, dict):
            logger.warning("LeverCrawler: skipping job — expected dict, got %s", type(item).__name__)
            return None

        title = item.get("text")
        if not title:
            logger.warning("LeverCrawler: skipping job — missing required field 'text'")
            return None

        job_id = item.get("id")
        if not job_id:
            logger.warning("LeverCrawler: skipping job — missing required field 'id'")
            return None

        hosted_url = item.get("hostedUrl")
        if not hosted_url:
            logger.warning("LeverCrawler: skipping job — missing required field 'hostedUrl'")
            return None

        company_id = item.get("_company_id")
        if not company_id:
            logger.warning(
                "LeverCrawler: skipping job — '_company_id' not injected (record was not produced by fetch())"
            )
            return None

        # location is nested under categories.location
        categories = item.get("categories")
        location_raw = (
            categories["location"]
            if isinstance(categories, dict) and categories.get("location")
            else None
        )
        location_normalized = normalize_location(location_raw, self.config.get("location_aliases"))

        # createdAt is milliseconds since Unix epoch — convert to UTC ISO-8601
        created_at_ms = item.get("createdAt")
        if isinstance(created_at_ms, (int, float)) and created_at_ms > 0:
            date_posted = (
                datetime.datetime.fromtimestamp(created_at_ms / 1000, tz=datetime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )
        else:
            date_posted = None

        # Prefer HTML description (strip tags); fall back to plain text description
        content = item.get("content") or {}
        description_html = content.get("descriptionHtml") if isinstance(content, dict) else None
        description_plain = content.get("description") if isinstance(content, dict) else None
        description = _strip_html(description_html) or (description_plain or None)

        return JobDict(
            title=str(title),
            company=str(company_id),
            source_url=str(hosted_url),
            ats_job_id=str(job_id),
            location=location_raw,
            location_normalized=location_normalized,
            description=description,
            date_posted=date_posted,
            source_name="lever",
        )


def _strip_html(html: str | None) -> str | None:
    """Convert an HTML string to plain text. Returns None for empty or absent input.

    Uses BeautifulSoup with the built-in html.parser. Separates block-level
    elements with a space so words do not run together after tag removal.

    Args:
        html: Raw HTML string from the Lever API descriptionHtml field, or None.

    Returns:
        Plain-text string with leading/trailing whitespace stripped,
        or None if the input is absent or results in an empty string.
    """
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
    return text if text else None
```

- [ ] **Step 6: Run parse() tests to confirm they pass**

```bash
pytest tests/test_crawler_lever.py -v -k "not fetch and not run"
```
Expected: All parse tests PASS.

---

## Task 3: fetch() and run() — confirm tests pass

- [ ] **Step 7: Run fetch() tests**

```bash
pytest tests/test_crawler_lever.py -v -k "fetch"
```
Expected: All fetch tests PASS.

- [ ] **Step 8: Run run() tests**

```bash
pytest tests/test_crawler_lever.py -v -k "run"
```
Expected: All run tests PASS.

- [ ] **Step 9: Run full Lever test suite**

```bash
pytest tests/test_crawler_lever.py -v
```
Expected: All tests PASS, zero failures.

- [ ] **Step 10: Run full project test suite for regressions**

```bash
pytest tests/ -v
```
Expected: All existing tests continue to PASS.

---

## Task 4: Commit

- [ ] **Step 11: Commit the Lever crawler**

```bash
git add src/crawlers/lever.py tests/fixtures/lever_response.json tests/test_crawler_lever.py
git commit -m "feat: add Lever ATS crawler with full test suite"
```

---

## Self-Review Checklist

### Spec coverage

| Requirement | Task coverage |
|---|---|
| Inherit BaseCrawler | ✅ Task 2 — `LeverCrawler(BaseCrawler)` |
| Use `http_client.get()` | ✅ Task 2/3 — `fetch()` calls `http_client.get()` |
| Emit `JobDict` objects | ✅ Task 2 — `parse()` returns `list[JobDict]` |
| Use `utils.normalize_location()` | ✅ Task 2 — `_parse_one` calls `normalize_location` |
| Strip HTML descriptions | ✅ Task 2 — `_strip_html` via BeautifulSoup on `descriptionHtml` |
| No database access | ✅ No `sqlite3` or `db.*` imports anywhere |
| No scoring access | ✅ No `scoring.*` imports |
| No notification access | ✅ No `notifications.*` imports |
| One malformed record must not fail the batch | ✅ `test_parse_malformed_record_does_not_fail_batch` |
| `lever_company_ids` from config (not hardcoded) | ✅ `fetch()` reads `self.config.get("lever_company_ids")` |
| Per-company fetch failure isolation | ✅ `test_fetch_skips_failed_company_continues_others` |
| Non-array Lever payload rejected gracefully | ✅ `test_fetch_skips_non_array_payload` |

### Placeholder scan
No TBD, TODO, "add appropriate X", or vague steps found.

### Type consistency
- `fetch()` returns `list[dict]` → matches `parse(raw: list[dict])` ✅
- `parse()` returns `list[JobDict]` → returned by `run()` ✅
- `_parse_one()` returns `JobDict | None` ✅
- `_strip_html()` signature `(str | None) -> str | None` matches both call sites ✅
