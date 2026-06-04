# Phase 4 — Crawler Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared crawler framework (exceptions, models, normalizer, HTTP client, base class, package init) that all source-specific crawlers will extend in Phases 5–7.

**Architecture:** Five focused modules with no cross-module coupling. `src/utils/normalizer.py` is a shared utility (not crawler-specific) importable by both crawlers and `pipeline/ingest.py`. Config is always passed explicitly as a parameter — never imported module-level (per DECISIONS.md). No source-specific logic anywhere.

**Tech Stack:** Python 3.10+, `requests`, `abc`, `TypedDict`, `unittest.mock` for tests, `pytest`.

---

## Approved Architecture Adjustments (2026-06-03)

1. **Normalizer location:** `src/utils/normalizer.py` (not `src/crawlers/`). Shared utility importable by both crawlers and ingest.
2. **`source_name` field:** Added as optional field in `JobDict`.
3. **Backoff cap:** `min(2 ** (attempt - 1), 16)` seconds between retries.
4. **Parse failure model:** Model B (per-record isolation).
   - Individual malformed records are logged and skipped.
   - Valid records from the same payload are still returned.
   - `CrawlerParseError` is reserved for structural payload failures only.
   - No minimum success percentage.
   - Log only crawler name and validation reason — do NOT dump the malformed record into the log.

---

## Scope

This plan creates only the shared framework. It does NOT implement `playwright_utils.py`, `greenhouse_crawler.py`, `lever_crawler.py`, or `workday_crawler.py`.

The `normalizer.py` module in `src/utils/` handles string cleanup and alias mapping. `pipeline/ingest.py` owns the `location_ineligible` decision.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/utils/__init__.py` | Create | Makes utils a package |
| `src/utils/normalizer.py` | Create | `normalize_location()` — pure function, maps raw → canonical location string |
| `src/crawlers/exceptions.py` | Create | `CrawlerFetchError`, `CrawlerParseError` typed exception classes |
| `src/crawlers/models.py` | Create | `JobDict` TypedDict — the shape of every job dict a crawler emits |
| `src/crawlers/http_client.py` | Create | `get()` — HTTP GET with retry, capped backoff, rate-limit, typed error raising |
| `src/crawlers/base.py` | Create | `BaseCrawler` — abstract class enforcing `fetch`/`parse`/`run` contract |
| `src/crawlers/__init__.py` | Modify | Expose public API from the package |
| `tests/test_utils_normalizer.py` | Create | Alias mapping, None, whitespace, case-insensitivity |
| `tests/test_crawler_exceptions.py` | Create | Exception class shape and behaviour |
| `tests/test_crawler_models.py` | Create | JobDict type and field access |
| `tests/test_crawler_http_client.py` | Create | Retry, capped backoff, rate-limit, error raising — all HTTP mocked |
| `tests/test_crawler_base.py` | Create | Abstract contract, run() error swallowing, Model B parse isolation |

---

## Strategies

### Interface

`get(url, headers=None, timeout=30, max_retries=3, rate_limit_delay=1.0) -> requests.Response`
All config values are explicit parameters — no module-level config import (DECISIONS.md).

`normalize_location(raw, location_aliases=None) -> str | None`
Returns the canonical string (or None). Does NOT set `location_ineligible` — that is ingest's job.

`BaseCrawler.__init__(self, config: dict)` stores config on `self`.
`run()` calls `fetch()` then `parse(raw)`. Catches `CrawlerFetchError`, `CrawlerParseError`, and any unexpected exception; logs each; returns `[]` on structural failure. For per-record errors inside `parse()`, the concrete crawler handles them internally (Model B).

### HTTP Retry

- Retryable status codes: `{429, 500, 502, 503, 504}`
- Non-retryable: all 4xx except 429, all 3xx — raise immediately (no retry)
- Network exceptions (`requests.RequestException`): retry
- Backoff between retries (not before first attempt): `min(2 ** (attempt - 1), 16)` seconds

| Retry | Backoff |
|---|---|
| 1st retry | 1s |
| 2nd retry | 2s |
| 3rd retry | 4s |
| 4th retry | 8s |
| 5th+ retry | 16s (capped) |

### Timeout

Default 30 seconds, passed explicitly. `requests.get(..., timeout=timeout)`.

### Rate Limiting

`time.sleep(rate_limit_delay)` runs before every request (first attempt and all retries). Default 1.0s. Callers pass 0 in tests.

### Error Handling — `BaseCrawler.run()`

- `CrawlerFetchError` from `fetch()`: log, return `[]`
- `CrawlerParseError` from `parse()`: log structural failure, return `[]`
- Unexpected exceptions from either: log, return `[]`
- Never re-raises to the scheduler

### Parse Failure Model (Model B — required)

`parse()` implementations in concrete crawlers must:
1. Iterate over all items in the raw payload
2. For each item: validate required fields. On failure, log `{CrawlerName}: skipping job — {reason}` and `continue`
3. Return the list of successfully parsed items (possibly partial)
4. Only raise `CrawlerParseError` if the entire payload structure is unusable (e.g., wrong type, missing top-level key)
5. Log the crawler name and validation reason only — never log the raw record content

### Test Strategy

- All HTTP calls patched via `unittest.mock.patch`
- No DB, no live HTTP, no filesystem writes
- `BaseCrawler` tests use concrete inner subclasses defined in the test file
- `TypedDict` is not enforced at runtime; tests verify dict access only
- Run command: `pytest tests/test_crawler_*.py tests/test_utils_normalizer.py -v`

---

## Task 1: Exception Classes

**Files:**
- Create: `src/crawlers/exceptions.py`
- Test: `tests/test_crawler_exceptions.py`

- [ ] **Step 1.1: Write the failing test**

```python
# tests/test_crawler_exceptions.py
"""Tests for src/crawlers/exceptions.py"""
import pytest

from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError


def test_crawler_fetch_error_is_exception():
    with pytest.raises(CrawlerFetchError):
        raise CrawlerFetchError("fetch failed")


def test_crawler_fetch_error_message():
    exc = CrawlerFetchError("bad status")
    assert str(exc) == "bad status"


def test_crawler_fetch_error_url_attribute():
    exc = CrawlerFetchError("bad status", url="https://example.com")
    assert exc.url == "https://example.com"


def test_crawler_fetch_error_url_defaults_to_empty_string():
    exc = CrawlerFetchError("bad status")
    assert exc.url == ""


def test_crawler_parse_error_is_exception():
    with pytest.raises(CrawlerParseError):
        raise CrawlerParseError("parse failed")


def test_crawler_parse_error_message():
    exc = CrawlerParseError("missing field")
    assert str(exc) == "missing field"


def test_crawler_parse_error_url_attribute():
    exc = CrawlerParseError("missing field", url="https://example.com/jobs")
    assert exc.url == "https://example.com/jobs"


def test_crawler_fetch_error_not_caught_as_parse_error():
    with pytest.raises(CrawlerFetchError):
        try:
            raise CrawlerFetchError("fetch")
        except CrawlerParseError:
            pass


def test_crawler_parse_error_not_caught_as_fetch_error():
    with pytest.raises(CrawlerParseError):
        try:
            raise CrawlerParseError("parse")
        except CrawlerFetchError:
            pass


def test_both_errors_are_exceptions():
    for cls in (CrawlerFetchError, CrawlerParseError):
        try:
            raise cls("msg")
        except Exception:
            pass
```

- [ ] **Step 1.2: Run test to confirm it fails**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_exceptions.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.crawlers.exceptions'`

- [ ] **Step 1.3: Write the implementation**

```python
# src/crawlers/exceptions.py
"""Typed exception classes for all crawler modules.

Inputs: message string; optional source URL.
Outputs: exception instances carrying .url attribute.
"""


class CrawlerFetchError(Exception):
    """Raised when an HTTP request or page render fails."""

    def __init__(self, message: str, url: str = "") -> None:
        super().__init__(message)
        self.url = url


class CrawlerParseError(Exception):
    """Raised when the entire payload structure is unusable."""

    def __init__(self, message: str, url: str = "") -> None:
        super().__init__(message)
        self.url = url
```

- [ ] **Step 1.4: Run test to confirm it passes**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_exceptions.py -v
```

Expected: all 10 tests PASSED.

---

## Task 2: Job Model

**Files:**
- Create: `src/crawlers/models.py`
- Test: `tests/test_crawler_models.py`

- [ ] **Step 2.1: Write the failing test**

```python
# tests/test_crawler_models.py
"""Tests for src/crawlers/models.py — JobDict structure."""
from src.crawlers.models import JobDict


def test_job_dict_is_importable():
    assert JobDict is not None


def test_job_dict_with_required_fields_only():
    job: JobDict = {
        "title": "Senior Data Engineer",
        "company": "ACME",
        "source_url": "https://acme.com/jobs/1",
    }
    assert job["title"] == "Senior Data Engineer"
    assert job["company"] == "ACME"
    assert job["source_url"] == "https://acme.com/jobs/1"


def test_job_dict_with_all_optional_fields():
    job: JobDict = {
        "title": "Senior Data Engineer",
        "company": "ACME",
        "source_url": "https://acme.com/jobs/1",
        "ats_job_id": "gh_12345",
        "location": "Gurgaon",
        "location_normalized": "Gurugram",
        "description": "We use PySpark for large-scale data processing.",
        "date_posted": "2026-06-01",
        "source_name": "greenhouse",
    }
    assert job["ats_job_id"] == "gh_12345"
    assert job["location"] == "Gurgaon"
    assert job["location_normalized"] == "Gurugram"
    assert job["source_name"] == "greenhouse"


def test_job_dict_optional_fields_can_be_none():
    job: JobDict = {
        "title": "Senior Data Engineer",
        "company": "ACME",
        "source_url": "https://acme.com/jobs/1",
        "ats_job_id": None,
        "location": None,
        "location_normalized": None,
        "description": None,
        "date_posted": None,
        "source_name": None,
    }
    assert job["ats_job_id"] is None
    assert job["source_name"] is None


def test_job_dict_is_plain_dict():
    job: JobDict = {
        "title": "t",
        "company": "c",
        "source_url": "u",
    }
    assert isinstance(job, dict)
```

- [ ] **Step 2.2: Run test to confirm it fails**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.crawlers.models'`

- [ ] **Step 2.3: Write the implementation**

```python
# src/crawlers/models.py
"""Job dict type shared across all crawlers.

Inputs: N/A — type definition only.
Outputs: JobDict TypedDict for use in type annotations.
"""
from typing import Optional, TypedDict


class _RequiredJobFields(TypedDict):
    title: str
    company: str
    source_url: str


class JobDict(_RequiredJobFields, total=False):
    """Job record emitted by crawlers. title, company, source_url are required."""

    ats_job_id: Optional[str]
    location: Optional[str]
    location_normalized: Optional[str]
    description: Optional[str]
    date_posted: Optional[str]
    source_name: Optional[str]
```

- [ ] **Step 2.4: Run test to confirm it passes**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_models.py -v
```

Expected: all 5 tests PASSED.

---

## Task 3: Location Normalizer

**Files:**
- Create: `src/utils/__init__.py`
- Create: `src/utils/normalizer.py`
- Test: `tests/test_utils_normalizer.py`

- [ ] **Step 3.1: Write the failing test**

```python
# tests/test_utils_normalizer.py
"""Tests for src/utils/normalizer.py — normalize_location pure function."""
from src.utils.normalizer import normalize_location


def test_none_input_returns_none():
    assert normalize_location(None) is None


def test_empty_string_returns_none():
    assert normalize_location("") is None


def test_whitespace_only_returns_none():
    assert normalize_location("   ") is None


def test_passthrough_when_no_aliases_provided():
    assert normalize_location("Gurugram") == "Gurugram"


def test_passthrough_when_aliases_is_none():
    assert normalize_location("Gurugram", location_aliases=None) == "Gurugram"


def test_passthrough_when_aliases_is_empty_dict():
    assert normalize_location("Gurugram", location_aliases={}) == "Gurugram"


def test_alias_mapped_to_canonical_form():
    aliases = {"gurgaon": "Gurugram"}
    assert normalize_location("Gurgaon", location_aliases=aliases) == "Gurugram"


def test_alias_match_is_case_insensitive():
    aliases = {"gurgaon": "Gurugram"}
    assert normalize_location("GURGAON", location_aliases=aliases) == "Gurugram"
    assert normalize_location("gurgaon", location_aliases=aliases) == "Gurugram"
    assert normalize_location("Gurgaon", location_aliases=aliases) == "Gurugram"


def test_unknown_location_returned_stripped():
    aliases = {"gurgaon": "Gurugram"}
    assert normalize_location("Bengaluru", location_aliases=aliases) == "Bengaluru"


def test_leading_trailing_whitespace_stripped_before_lookup():
    assert normalize_location("  Remote  ") == "Remote"


def test_alias_applied_after_stripping_whitespace():
    aliases = {"gurgaon": "Gurugram"}
    assert normalize_location("  Gurgaon  ", location_aliases=aliases) == "Gurugram"


def test_second_alias_mapped_independently():
    aliases = {"gurgaon": "Gurugram", "bombay": "Mumbai"}
    assert normalize_location("Bombay", location_aliases=aliases) == "Mumbai"
    assert normalize_location("Gurgaon", location_aliases=aliases) == "Gurugram"
```

- [ ] **Step 3.2: Run test to confirm it fails**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_utils_normalizer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.utils'`

- [ ] **Step 3.3: Write the implementation**

Create `src/utils/__init__.py` (empty).

```python
# src/utils/normalizer.py
"""Location string normalization shared across crawlers and pipeline.

Inputs: raw location string (or None); optional alias dict {raw_lower: canonical}.
Outputs: canonical location string, or None if raw is None/empty.
No database access. No config import. Pure function.
"""
from __future__ import annotations


def normalize_location(
    raw: str | None,
    location_aliases: dict[str, str] | None = None,
) -> str | None:
    """Map a raw location string to a canonical form using provided aliases.

    Args:
        raw: Raw location string from source. May be None or empty.
        location_aliases: Mapping of {lowercase_raw: canonical}. Case-insensitive.

    Returns:
        Canonical location string with whitespace stripped, or None for empty input.
    """
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if not location_aliases:
        return stripped
    return location_aliases.get(stripped.lower(), stripped)
```

- [ ] **Step 3.4: Run test to confirm it passes**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_utils_normalizer.py -v
```

Expected: all 12 tests PASSED.

---

## Task 4: HTTP Client

**Files:**
- Create: `src/crawlers/http_client.py`
- Test: `tests/test_crawler_http_client.py`

- [ ] **Step 4.1: Write the failing test**

```python
# tests/test_crawler_http_client.py
"""Tests for src/crawlers/http_client.py — all HTTP calls mocked."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.crawlers.exceptions import CrawlerFetchError
from src.crawlers.http_client import get


def _make_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    return resp


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_successful_200_returns_response(mock_get, mock_sleep):
    mock_get.return_value = _make_response(200)
    result = get("https://example.com", max_retries=1, rate_limit_delay=0)
    assert result.status_code == 200


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_non_retryable_404_raises_without_retry(mock_get, mock_sleep):
    mock_get.return_value = _make_response(404)
    with pytest.raises(CrawlerFetchError):
        get("https://example.com", max_retries=3, rate_limit_delay=0)
    assert mock_get.call_count == 1


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_non_retryable_403_raises_without_retry(mock_get, mock_sleep):
    mock_get.return_value = _make_response(403)
    with pytest.raises(CrawlerFetchError):
        get("https://example.com", max_retries=3, rate_limit_delay=0)
    assert mock_get.call_count == 1


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_500_retried_succeeds_on_second_attempt(mock_get, mock_sleep):
    mock_get.side_effect = [_make_response(500), _make_response(200)]
    result = get("https://example.com", max_retries=2, rate_limit_delay=0)
    assert result.status_code == 200
    assert mock_get.call_count == 2


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_500_all_retries_exhausted_raises(mock_get, mock_sleep):
    mock_get.return_value = _make_response(500)
    with pytest.raises(CrawlerFetchError):
        get("https://example.com", max_retries=3, rate_limit_delay=0)
    assert mock_get.call_count == 3


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_429_is_retried(mock_get, mock_sleep):
    mock_get.side_effect = [_make_response(429), _make_response(200)]
    result = get("https://example.com", max_retries=2, rate_limit_delay=0)
    assert result.status_code == 200
    assert mock_get.call_count == 2


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_502_is_retried(mock_get, mock_sleep):
    mock_get.side_effect = [_make_response(502), _make_response(200)]
    result = get("https://example.com", max_retries=2, rate_limit_delay=0)
    assert result.status_code == 200


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_connection_error_retried_then_raises(mock_get, mock_sleep):
    mock_get.side_effect = requests.ConnectionError("refused")
    with pytest.raises(CrawlerFetchError):
        get("https://example.com", max_retries=1, rate_limit_delay=0)


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_timeout_raises_crawler_fetch_error(mock_get, mock_sleep):
    mock_get.side_effect = requests.Timeout("timed out")
    with pytest.raises(CrawlerFetchError):
        get("https://example.com", max_retries=1, rate_limit_delay=0)


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_connection_error_succeeds_on_retry(mock_get, mock_sleep):
    mock_get.side_effect = [requests.ConnectionError("refused"), _make_response(200)]
    result = get("https://example.com", max_retries=2, rate_limit_delay=0)
    assert result.status_code == 200


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_rate_limit_delay_applied_before_first_request(mock_get, mock_sleep):
    mock_get.return_value = _make_response(200)
    get("https://example.com", max_retries=1, rate_limit_delay=1.5)
    mock_sleep.assert_any_call(1.5)


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_error_carries_url(mock_get, mock_sleep):
    mock_get.return_value = _make_response(404)
    with pytest.raises(CrawlerFetchError) as exc_info:
        get("https://api.example.com/jobs", max_retries=1, rate_limit_delay=0)
    assert exc_info.value.url == "https://api.example.com/jobs"


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_backoff_capped_at_16s(mock_get, mock_sleep):
    # With 7 retries, backoff values should be 1,2,4,8,16,16,16 — never exceed 16s
    mock_get.return_value = _make_response(500)
    with pytest.raises(CrawlerFetchError):
        get("https://example.com", max_retries=7, rate_limit_delay=0)
    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
    backoff_calls = [s for s in sleep_calls if s > 0]
    assert all(s <= 16 for s in backoff_calls)


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_headers_passed_through(mock_get, mock_sleep):
    mock_get.return_value = _make_response(200)
    headers = {"User-Agent": "TestBot/1.0"}
    get("https://example.com", headers=headers, max_retries=1, rate_limit_delay=0)
    _, kwargs = mock_get.call_args
    assert kwargs.get("headers") == headers
```

- [ ] **Step 4.2: Run test to confirm it fails**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_http_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.crawlers.http_client'`

- [ ] **Step 4.3: Write the implementation**

```python
# src/crawlers/http_client.py
"""Shared HTTP GET with retry, capped backoff, rate-limit, and typed error raising.

Inputs: URL; optional headers, timeout, max_retries, rate_limit_delay.
Outputs: requests.Response on HTTP 200; raises CrawlerFetchError on any failure.
No database access. No config import — all values are explicit parameters.
"""
from __future__ import annotations

import logging
import time

import requests

from src.crawlers.exceptions import CrawlerFetchError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_MAX_BACKOFF_SECONDS: int = 16


def get(
    url: str,
    headers: dict | None = None,
    timeout: int = 30,
    max_retries: int = 3,
    rate_limit_delay: float = 1.0,
) -> requests.Response:
    """Send an HTTP GET request with retry and rate-limit delay.

    Args:
        url: URL to fetch.
        headers: Optional HTTP headers dict.
        timeout: Request timeout in seconds.
        max_retries: Total number of attempts before raising.
        rate_limit_delay: Seconds to sleep before every attempt.

    Returns:
        requests.Response with status_code 200.

    Raises:
        CrawlerFetchError: Non-200 response or network error after all retries.
    """
    last_error = "unknown error"

    for attempt in range(max_retries):
        if attempt > 0:
            backoff = min(2 ** (attempt - 1), _MAX_BACKOFF_SECONDS)
            time.sleep(backoff)

        time.sleep(rate_limit_delay)
        logger.info("GET %s (attempt %d/%d)", url, attempt + 1, max_retries)

        try:
            response = requests.get(url, headers=headers or {}, timeout=timeout)
        except requests.RequestException as exc:
            last_error = str(exc)
            logger.warning("Network error fetching %s: %s", url, last_error)
            continue

        if response.status_code == 200:
            return response

        last_error = f"HTTP {response.status_code}"
        logger.warning("Non-200 response %s from %s", response.status_code, url)

        if response.status_code not in _RETRYABLE_STATUS_CODES:
            raise CrawlerFetchError(last_error, url=url)

    raise CrawlerFetchError(
        f"All {max_retries} attempts failed — {last_error}", url=url
    )
```

- [ ] **Step 4.4: Run test to confirm it passes**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_http_client.py -v
```

Expected: all 14 tests PASSED.

---

## Task 5: Base Crawler

**Files:**
- Create: `src/crawlers/base.py`
- Test: `tests/test_crawler_base.py`

NOTE: The `BaseCrawler.run()` method catches structural errors from `parse()`. Per-record isolation (Model B) is a responsibility of concrete crawler implementations, not of the framework's `run()` method. The test for Model B in this task validates the pattern using a concrete test subclass.

- [ ] **Step 5.1: Write the failing test**

```python
# tests/test_crawler_base.py
"""Tests for src/crawlers/base.py — BaseCrawler abstract contract."""
import pytest

from src.crawlers.base import BaseCrawler
from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.models import JobDict


# --- Concrete subclasses used only in tests ---

class _WorkingCrawler(BaseCrawler):
    def fetch(self):
        return [
            {"title": "Data Engineer", "company": "ACME", "source_url": "https://acme.com/1"},
            {"title": "Analytics Engineer", "company": "ACME", "source_url": "https://acme.com/2"},
        ]

    def parse(self, raw) -> list[JobDict]:
        return raw


class _FetchErrorCrawler(BaseCrawler):
    def fetch(self):
        raise CrawlerFetchError("connection refused", url="https://example.com")

    def parse(self, raw) -> list[JobDict]:
        return raw


class _ParseErrorCrawler(BaseCrawler):
    """Simulates structural payload failure — entire payload unusable."""
    def fetch(self):
        return "not a list"

    def parse(self, raw) -> list[JobDict]:
        raise CrawlerParseError("expected list, got str", url="https://example.com")


class _ModelBCrawler(BaseCrawler):
    """Simulates Model B: skips malformed records, returns valid ones."""
    def fetch(self):
        return [
            {"title": "Data Engineer", "company": "ACME", "source_url": "https://acme.com/1"},
            {"company": "ACME", "source_url": "https://acme.com/2"},  # missing title
            {"title": "Analytics Engineer", "company": "ACME", "source_url": "https://acme.com/3"},
        ]

    def parse(self, raw) -> list[JobDict]:
        results = []
        for item in raw:
            if not item.get("title"):
                continue  # skip malformed
            results.append(item)
        return results


class _UnexpectedFetchErrorCrawler(BaseCrawler):
    def fetch(self):
        raise RuntimeError("unexpected failure in fetch")

    def parse(self, raw) -> list[JobDict]:
        return raw


class _UnexpectedParseErrorCrawler(BaseCrawler):
    def fetch(self):
        return {}

    def parse(self, raw) -> list[JobDict]:
        raise ValueError("unexpected failure in parse")


# --- Abstract contract ---

def test_cannot_instantiate_base_crawler_directly():
    with pytest.raises(TypeError):
        BaseCrawler({})


def test_cannot_instantiate_without_fetch_implemented():
    class _NoFetch(BaseCrawler):
        def parse(self, raw) -> list[JobDict]:
            return []
    with pytest.raises(TypeError):
        _NoFetch({})


def test_cannot_instantiate_without_parse_implemented():
    class _NoParse(BaseCrawler):
        def fetch(self):
            return []
    with pytest.raises(TypeError):
        _NoParse({})


# --- run() success path ---

def test_run_returns_list_on_success():
    result = _WorkingCrawler({}).run()
    assert isinstance(result, list)


def test_run_returns_all_job_dicts_on_success():
    result = _WorkingCrawler({}).run()
    assert len(result) == 2
    assert result[0]["title"] == "Data Engineer"
    assert result[1]["title"] == "Analytics Engineer"


# --- run() error swallowing ---

def test_run_returns_empty_list_on_crawler_fetch_error():
    assert _FetchErrorCrawler({}).run() == []


def test_run_returns_empty_list_on_crawler_parse_error():
    assert _ParseErrorCrawler({}).run() == []


def test_run_returns_empty_list_on_unexpected_fetch_error():
    assert _UnexpectedFetchErrorCrawler({}).run() == []


def test_run_returns_empty_list_on_unexpected_parse_error():
    assert _UnexpectedParseErrorCrawler({}).run() == []


def test_run_does_not_raise_on_fetch_error():
    _FetchErrorCrawler({}).run()


def test_run_does_not_raise_on_parse_error():
    _ParseErrorCrawler({}).run()


# --- Model B: per-record isolation ---

def test_run_returns_valid_records_when_some_malformed():
    result = _ModelBCrawler({}).run()
    assert len(result) == 2
    titles = [j["title"] for j in result]
    assert "Data Engineer" in titles
    assert "Analytics Engineer" in titles


def test_run_does_not_return_malformed_records():
    result = _ModelBCrawler({}).run()
    for job in result:
        assert "title" in job and job["title"]


# --- Config storage ---

def test_config_stored_on_instance():
    config = {"notification_threshold": 20, "accepted_locations": ["Remote"]}
    crawler = _WorkingCrawler(config)
    assert crawler.config == config


def test_empty_config_accepted():
    crawler = _WorkingCrawler({})
    assert crawler.config == {}
```

- [ ] **Step 5.2: Run test to confirm it fails**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.crawlers.base'`

- [ ] **Step 5.3: Write the implementation**

```python
# src/crawlers/base.py
"""Abstract BaseCrawler enforcing the fetch/parse/run contract.

Inputs: config dict passed at instantiation.
Outputs: run() returns list[JobDict], never raises.
Parse failure isolation (Model B) is a responsibility of concrete subclasses.
"""
from __future__ import annotations

import abc
import logging
from typing import Any

from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.models import JobDict

logger = logging.getLogger(__name__)


class BaseCrawler(abc.ABC):
    """Abstract base for all source-specific crawlers.

    Subclasses must implement fetch() and parse(raw).
    run() orchestrates both and swallows all errors, returning [] on failure.
    Concrete parse() implementations must follow Model B: per-record isolation.
    """

    def __init__(self, config: dict) -> None:
        self.config = config

    @abc.abstractmethod
    def fetch(self) -> Any:
        """Fetch raw data from the source. Return type is source-specific."""

    @abc.abstractmethod
    def parse(self, raw: Any) -> list[JobDict]:
        """Parse raw data into a list of job dicts.

        Must implement Model B: skip malformed records (log reason only),
        return valid records. Raise CrawlerParseError only for structural failures.
        """

    def run(self) -> list[JobDict]:
        """Fetch then parse. Returns [] on any error — never raises to the caller."""
        try:
            raw = self.fetch()
        except CrawlerFetchError as exc:
            logger.error("%s fetch failed: %s", self.__class__.__name__, exc)
            return []
        except Exception as exc:
            logger.error("%s unexpected fetch error: %s", self.__class__.__name__, exc)
            return []

        try:
            return self.parse(raw)
        except CrawlerParseError as exc:
            logger.error("%s structural parse failure: %s", self.__class__.__name__, exc)
            return []
        except Exception as exc:
            logger.error("%s unexpected parse error: %s", self.__class__.__name__, exc)
            return []
```

- [ ] **Step 5.4: Run test to confirm it passes**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_base.py -v
```

Expected: all 15 tests PASSED.

---

## Task 6: Package Init

**Files:**
- Modify: `src/crawlers/__init__.py`

- [ ] **Step 6.1: Write the implementation**

```python
# src/crawlers/__init__.py
"""Crawler framework — public API."""
from src.crawlers.base import BaseCrawler
from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.models import JobDict

__all__ = ["BaseCrawler", "CrawlerFetchError", "CrawlerParseError", "JobDict"]
```

- [ ] **Step 6.2: Run smoke test**

```bash
cd /Users/tanshu/Jobapplication && python -c "
from src.crawlers import BaseCrawler, CrawlerFetchError, CrawlerParseError, JobDict
print('BaseCrawler:', BaseCrawler)
print('CrawlerFetchError:', CrawlerFetchError)
print('CrawlerParseError:', CrawlerParseError)
print('JobDict:', JobDict)
print('All imports OK')
"
```

---

## Task 7: Full Test Run

- [ ] **Step 7.1: Run the complete framework test suite**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/test_crawler_exceptions.py tests/test_crawler_models.py tests/test_utils_normalizer.py tests/test_crawler_http_client.py tests/test_crawler_base.py -v
```

Expected: all tests PASSED, 0 failures, 0 errors.

- [ ] **Step 7.2: Confirm existing tests are unaffected**

```bash
cd /Users/tanshu/Jobapplication && pytest tests/ -v
```

Expected: all previously passing tests still PASSED.

---

## Self-Review Checklist

### Spec Coverage

| Requirement | Covered by |
|---|---|
| `crawlers/base.py` — abstract BaseCrawler | Task 5 |
| `crawlers/http_client.py` — retry, capped backoff, rate-limit, typed errors | Task 4 |
| `crawlers/models.py` — job dict with source_name | Task 2 |
| `utils/normalizer.py` — normalization as shared utility | Task 3 |
| `crawlers/__init__.py` — public exports | Task 6 |
| Model B parse failure isolation | Task 5 tests |
| Backoff capped at 16s | Task 4 test `test_backoff_capped_at_16s` |
| No source-specific logic | No ATS imports in any module |
| No DB access | No `sqlite3` imports anywhere |
| No scoring access | No `scoring.*` imports |
| No notification access | No `notifications.*` imports |
| Config as explicit params | `get()` and `BaseCrawler.__init__` both receive config as params |

### Forbidden Import Verification

- `exceptions.py`: builtins only
- `models.py`: `typing` only
- `normalizer.py`: `__future__` only
- `http_client.py`: `requests`, `time`, `logging`, `crawlers.exceptions`
- `base.py`: `abc`, `logging`, `typing`, `crawlers.exceptions`, `crawlers.models`
- `__init__.py`: within-package imports only
- `utils/normalizer.py`: `__future__` only
