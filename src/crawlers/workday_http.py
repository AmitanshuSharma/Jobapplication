# src/crawlers/workday_http.py
"""HTTP POST client for Workday CXS API requests.

Dedicated POST implementation with retry/backoff identical to http_client.get().
Kept separate to avoid modifying http_client.py.

Inputs: URL; optional JSON payload, headers, timeout, max_retries, rate_limit_delay.
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


def post(
    url: str,
    json_payload: dict | None = None,
    headers: dict | None = None,
    timeout: int = 30,
    max_retries: int = 3,
    rate_limit_delay: float = 1.0,
) -> requests.Response:
    """Send an HTTP POST request with retry and rate-limit delay.

    Args:
        url: URL to POST to.
        json_payload: Dict serialised as JSON request body.
        headers: Optional HTTP headers dict.
        timeout: Request timeout in seconds.
        max_retries: Total number of attempts. Must be >= 1.
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
        logger.info("POST %s (attempt %d/%d)", url, attempt + 1, max_retries)

        try:
            response = requests.post(url, json=json_payload, headers=headers or {}, timeout=timeout)
        except requests.RequestException as exc:
            last_error = str(exc)
            logger.warning("Network error posting to %s: %s", url, last_error)
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
