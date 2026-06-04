# Greenhouse Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `GreenhouseCrawler` — a `BaseCrawler` subclass that fetches open roles from the Greenhouse public board API, parses them into `JobDict` objects, and isolates malformed records so one bad listing never fails the batch.

**Architecture:** `fetch()` iterates configured board tokens, calls the Greenhouse list endpoint for each (injecting `_company_name` into each raw job dict), and returns a flat list. `parse()` validates required fields per record (Model B), applies location normalization, and returns valid `JobDict` objects. No database access, no scoring, no notifications.

**Tech Stack:** Python 3.10+, `requests` (via `http_client`), `unittest.mock`, `pytest`, existing `BaseCrawler` / `JobDict` / `normalize_location` framework.

---

## Naming note

The user-facing task says `crawlers/greenhouse.py`. Project docs (ARCHITECTURE.md, MODULES.md) say `greenhouse_crawler.py`. **This plan uses `greenhouse.py`** as specified in the task brief. If the naming must align with the docs, rename before merging.

---

## Greenhouse API — verified payload shape

Endpoint: `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`

The `?content=true` parameter includes the full job description in the list response, avoiding a second per-job API call.

```json
{
  "jobs": [
    {
      "id": 4037389005,
      "title": "Senior Data Engineer",
      "updated_at": "2026-05-28T10:00:00-05:00",
      "requisition_id": "DE-2026-001",
      "location": { "name": "Gurugram, India" },
      "departments": [{ "id": 4001, "name": "Engineering" }],
      "offices":    [{ "id": 5001, "name": "India - Gurugram" }],
      "absolute_url": "https://boards.greenhouse.io/acme/jobs/4037389005",
      "content": "<p>Job description HTML…</p>",
      "metadata": []
    }
  ]
}
```

Field mapping to `JobDict`:

| Greenhouse field   | `JobDict` field       | Notes                                      |
|--------------------|-----------------------|--------------------------------------------|
| `id`               | `ats_job_id`          | Integer → cast to `str`                    |
| `title`            | `title`               | Required — skip record if absent           |
| `absolute_url`     | `source_url`          | Required — skip record if absent           |
| `_company_name`    | `company`             | Injected by `fetch()` from config dict key |
| `location.name`    | `location`            | Raw string; `None` if absent               |
| `location.name`    | `location_normalized` | Via `normalize_location()`                 |
| `content`          | `description`         | Optional; `None` if empty                  |
| `updated_at`       | `date_posted`         | Optional; `None` if absent                 |
| `"greenhouse"`     | `source_name`         | Literal constant                           |

**Required fields** (record is skipped if any are missing/falsy): `title`, `id`, `absolute_url`, `_company_name`.

---

## Config keys used

From `config.yaml` (see `config/config.yaml.example`):

```yaml
greenhouse_board_tokens:         # dict: display_name → board_token
  acme: acme-token
  beta: beta-token

request_timeout_seconds: 30      # optional; default 30
max_retries: 3                   # optional; default 3
user_agent: JobIntelligencePlatform/1.0   # optional

location_aliases:                # optional; passed to normalize_location()
  "gurgaon, india": Gurugram
```

`greenhouse_board_tokens` is a **dict** (display name → board token), not a list.

---

## File Map

| File                                      | Action | Responsibility                                           |
|-------------------------------------------|--------|----------------------------------------------------------|
| `src/crawlers/greenhouse.py`              | Create | `GreenhouseCrawler` — fetch + parse Greenhouse API       |
| `tests/fixtures/greenhouse_response.json` | Create | Fixture JSON for parse/run tests (no live network calls) |
| `tests/test_crawler_greenhouse.py`        | Create | All unit tests — HTTP fully mocked                       |

No existing files are modified.

---

## Malformed record handling (Model B)

`parse()` calls `_parse_one(item)` for each raw dict.  
`_parse_one` checks required fields explicitly and returns `None` on failure, logging `"GreenhouseCrawler: skipping job — {reason}"`. Raw record content is never logged (DECISIONS.md).  
`parse()` appends only non-`None` results.  
`CrawlerParseError` is raised only if `raw` itself is not a `list` (structural failure upstream from `fetch()`).

One failed token in `fetch()` logs and continues — remaining tokens are still fetched.

---

## Task 1: Create fixture file

**Files:**
- Create: `tests/fixtures/greenhouse_response.json`

- [ ] **Step 1.1: Write the fixture file**

```json
{
  "jobs": [
    {
      "id": 4037389005,
      "title": "Senior Data Engineer",
      "updated_at": "2026-05-28T10:00:00-05:00",
      "requisition_id": "DE-2026-001",
      "location": { "name": "Gurugram, India" },
      "departments": [{ "id": 4001, "name": "Engineering" }],
      "offices":    [{ "id": 5001, "name": "India - Gurugram" }],
      "absolute_url": "https://boards.greenhouse.io/acme/jobs/4037389005",
      "content": "<p>Senior Data Engineer with PySpark and Databricks experience.</p>",
      "metadata": []
    },
    {
      "id": 4037389006,
      "title": "Analytics Engineer",
      "updated_at": "2026-05-27T08:00:00-05:00",
      "requisition_id": "AE-2026-002",
      "location": { "name": "Remote" },
      "departments": [{ "id": 4001, "name": "Engineering" }],
      "offices":    [],
      "absolute_url": "https://boards.greenhouse.io/acme/jobs/4037389006",
      "content": "<p>Analytics Engineer with dbt and Snowflake.</p>",
      "metadata": []
    }
  ]
}
```

Save to: `tests/fixtures/greenhouse_response.json`

---

## Task 2: Write the failing tests

**Files:**
- Create: `tests/test_crawler_greenhouse.py`
- Test: `src/crawlers/greenhouse.py` (does not exist yet — tests must fail)

- [ ] **Step 2.1: Write the test file**

```python
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


def test_parse_skips_record_missing_title():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [
        # missing title
        {"id": 1, "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "_company_name": "acme"},
        {"id": 2, "title": "Data Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/2", "_company_name": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Data Engineer"


def test_parse_skips_record_missing_id():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [
        # missing id
        {"title": "Data Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "_company_name": "acme"},
        {"id": 2, "title": "Analytics Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/2", "_company_name": "acme"},
    ]
    result = crawler.parse(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Analytics Engineer"


def test_parse_skips_record_missing_absolute_url():
    crawler = GreenhouseCrawler(_BASE_CONFIG)
    raw = [
        # missing absolute_url
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
    assert result[0]["date_posted"] == "2026-05-28T10:00:00-05:00"


# ---------------------------------------------------------------------------
# fetch() tests (HTTP mocked)
# ---------------------------------------------------------------------------


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_calls_greenhouse_api_url(mock_get):
    mock_get.return_value = _mock_response({"jobs": []})
    GreenhouseCrawler({"greenhouse_board_tokens": {"acme": "acme-token"}, "max_retries": 1}).fetch()
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
    result = GreenhouseCrawler({"greenhouse_board_tokens": {"acme-corp": "acme-token"}, "max_retries": 1}).fetch()
    assert result[0]["_company_name"] == "acme-corp"


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_skips_failed_token_continues_others(mock_get):
    """CrawlerFetchError from one token must not stop remaining tokens."""
    good_payload = {"jobs": [
        {"id": 1, "title": "Data Engineer", "absolute_url": "https://boards.greenhouse.io/beta/jobs/1"},
    ]}
    mock_get.side_effect = [CrawlerFetchError("refused"), _mock_response(good_payload)]
    config = {
        "greenhouse_board_tokens": {"acme": "acme-token", "beta": "beta-token"},
        "max_retries": 1,
    }
    result = GreenhouseCrawler(config).fetch()
    assert len(result) == 1
    assert result[0]["title"] == "Data Engineer"


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
    result = GreenhouseCrawler({"greenhouse_board_tokens": {"acme": "acme-token"}, "max_retries": 1}).fetch()
    assert result == []


@patch("src.crawlers.greenhouse.http_client.get")
def test_fetch_flattens_jobs_from_multiple_tokens(mock_get):
    payload_a = {"jobs": [{"id": 1, "title": "Job A", "absolute_url": "https://boards.greenhouse.io/a/jobs/1"}]}
    payload_b = {"jobs": [{"id": 2, "title": "Job B", "absolute_url": "https://boards.greenhouse.io/b/jobs/2"},
                          {"id": 3, "title": "Job C", "absolute_url": "https://boards.greenhouse.io/b/jobs/3"}]}
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


@patch("src.crawlers.greenhouse.http_client.get")
def test_run_does_not_raise(mock_get):
    mock_get.side_effect = CrawlerFetchError("refused")
    GreenhouseCrawler(_BASE_CONFIG).run()  # must not raise
```

- [ ] **Step 2.2: Run tests to confirm they fail (module not found)**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_greenhouse.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'src.crawlers.greenhouse'`

---

## Task 3: Implement `src/crawlers/greenhouse.py`

**Files:**
- Create: `src/crawlers/greenhouse.py`

- [ ] **Step 3.1: Write the implementation**

```python
# src/crawlers/greenhouse.py
"""Greenhouse public job board API crawler.

Inputs:  config dict — greenhouse_board_tokens (dict), request settings, location_aliases.
Outputs: list[JobDict] from run() — one entry per valid open role found.
No database access. No scoring. No notifications. No Playwright.
"""
from __future__ import annotations

import logging

from src.crawlers import http_client
from src.crawlers.base import BaseCrawler
from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.models import JobDict
from src.utils.normalizer import normalize_location

logger = logging.getLogger(__name__)

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


class GreenhouseCrawler(BaseCrawler):
    """Fetches open roles from the Greenhouse public board API.

    Config keys:
        greenhouse_board_tokens (dict): {display_name: board_token} pairs.
        request_timeout_seconds (int): HTTP timeout in seconds. Default 30.
        max_retries (int): Retry attempts per URL. Default 3.
        user_agent (str): User-Agent header value.
        location_aliases (dict): Passed to normalize_location(). Optional.
    """

    def fetch(self) -> list[dict]:
        """Fetch raw job dicts from all configured Greenhouse board tokens.

        Calls the Greenhouse jobs list endpoint for each board token. Injects
        '_company_name' into each raw job dict so parse() can set the company field.
        A CrawlerFetchError for one token is logged and skipped; others continue.

        Returns:
            Flat list of raw job dicts from all successful API responses.
        """
        board_tokens: dict[str, str] = self.config.get("greenhouse_board_tokens") or {}
        raw_jobs: list[dict] = []

        for company_name, board_token in board_tokens.items():
            url = _BASE_URL.format(token=board_token)
            try:
                response = http_client.get(
                    url,
                    headers={"User-Agent": self.config.get("user_agent", "JobIntelligencePlatform/1.0")},
                    timeout=self.config.get("request_timeout_seconds", 30),
                    max_retries=self.config.get("max_retries", 3),
                )
            except CrawlerFetchError as exc:
                logger.error("GreenhouseCrawler: fetch failed for %s — %s", company_name, exc)
                continue

            try:
                payload = response.json()
            except Exception as exc:
                logger.error("GreenhouseCrawler: invalid JSON from %s — %s", url, exc)
                continue

            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                logger.error("GreenhouseCrawler: unexpected payload shape from %s", url)
                continue

            for job in payload["jobs"]:
                job["_company_name"] = company_name
                raw_jobs.append(job)

        return raw_jobs

    def parse(self, raw: list[dict]) -> list[JobDict]:
        """Parse a flat list of raw Greenhouse job dicts into JobDict objects.

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
                f"GreenhouseCrawler: expected list from fetch(), got {type(raw).__name__}"
            )

        results: list[JobDict] = []
        for item in raw:
            job = self._parse_one(item)
            if job is not None:
                results.append(job)
        return results

    def _parse_one(self, item: dict) -> JobDict | None:
        """Validate and map a single raw job dict to a JobDict.

        Returns None (and logs the reason) if any required field is absent.
        Never logs raw record content — logs the skip reason only (DECISIONS.md).

        Args:
            item: Single raw job dict from the Greenhouse API response.

        Returns:
            Populated JobDict on success, None on validation failure.
        """
        title = item.get("title")
        if not title:
            logger.warning("GreenhouseCrawler: skipping job — missing required field 'title'")
            return None

        job_id = item.get("id")
        if not job_id:
            logger.warning("GreenhouseCrawler: skipping job — missing required field 'id'")
            return None

        absolute_url = item.get("absolute_url")
        if not absolute_url:
            logger.warning("GreenhouseCrawler: skipping job — missing required field 'absolute_url'")
            return None

        company = item.get("_company_name")
        if not company:
            logger.warning("GreenhouseCrawler: skipping job — missing company name")
            return None

        # location is a nested dict in the Greenhouse response; guard against non-dict values
        location_obj = item.get("location")
        location_raw = (
            location_obj["name"]
            if isinstance(location_obj, dict) and location_obj.get("name")
            else None
        )
        location_normalized = normalize_location(location_raw, self.config.get("location_aliases"))

        return JobDict(
            title=str(title),
            company=str(company),
            source_url=str(absolute_url),
            ats_job_id=str(job_id),
            location=location_raw,
            location_normalized=location_normalized,
            description=item.get("content") or None,
            date_posted=item.get("updated_at") or None,
            source_name="greenhouse",
        )
```

---

## Task 4: Run Greenhouse tests

- [ ] **Step 4.1: Run tests to confirm they pass**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_greenhouse.py -v
```

Expected: all tests PASSED, 0 failures, 0 errors.

- [ ] **Step 4.2: Confirm no forbidden imports**

```bash
cd /Users/tanshu/Jobapplication && python -c "
import ast, sys
tree = ast.parse(open('src/crawlers/greenhouse.py').read())
imports = [
    n.names[0].name if isinstance(n, ast.Import) else n.module
    for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
]
forbidden = [i for i in imports if i and any(
    i.startswith(f) for f in ('sqlite3', 'pipeline', 'db.', 'scoring', 'notifications', 'dashboard', 'playwright')
)]
if forbidden:
    print('FORBIDDEN IMPORTS:', forbidden); sys.exit(1)
else:
    print('No forbidden imports found.')
"
```

Expected: `No forbidden imports found.`

---

## Task 5: Run full test suite

- [ ] **Step 5.1: Run all tests**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/ -v
```

Expected: all previously passing tests still PASSED, plus all greenhouse tests PASSED.

---

## Self-Review

### Spec Coverage

| Requirement | Covered by |
|---|---|
| Inherit `BaseCrawler` | `GreenhouseCrawler(BaseCrawler)` in implementation |
| Use `http_client.get()` | `fetch()` calls `http_client.get(url, ...)` per board token |
| Emit `JobDict` objects | `parse()` returns `list[JobDict]` |
| Use `utils.normalize_location()` | `_parse_one()` calls `normalize_location()` |
| No database access | No `sqlite3` / `db.*` imports |
| No scoring access | No `scoring.*` imports |
| No notification access | No `notifications.*` imports |
| No hardcoded company logic | Board tokens come from `config["greenhouse_board_tokens"]` |
| One malformed record must not fail the batch | `_parse_one()` returns `None`; `parse()` skips `None` results |
| `CrawlerParseError` for structural failure only | Raised only when `raw` is not a `list` |
| `CrawlerFetchError` per token (not global) | `fetch()` catches per-token, continues |
| Tests — HTTP mocked | All `http_client.get` calls patched via `unittest.mock.patch` |
| Tests — no DB | No `sqlite3` in test file |
| Tests — no live HTTP | Fixture file used; mock used for fetch tests |
| Fixture covers verified API shape | `greenhouse_response.json` matches documented API payload |

### Placeholder scan

No TBD, TODO, or fill-in-later items in any task.

### Type consistency

- `_BASE_CONFIG` defined once in test file, reused across all tests.
- `_parse_one` returns `JobDict | None` — matches `parse()` loop logic.
- `_mock_response` returns a `MagicMock` with `.json()` method — matches `response.json()` call in `fetch()`.
- Patch target `src.crawlers.greenhouse.http_client.get` matches the import `from src.crawlers import http_client` in `greenhouse.py`.
