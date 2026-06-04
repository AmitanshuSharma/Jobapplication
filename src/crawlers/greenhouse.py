# src/crawlers/greenhouse.py
"""Greenhouse public job board API crawler.

Inputs:  config dict — greenhouse_board_tokens (dict), request settings, location_aliases.
Outputs: list[JobDict] from run() — one entry per valid open role found.
No database access. No scoring. No notifications. No Playwright.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from src.crawlers import http_client
from src.crawlers.base import BaseCrawler
from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.models import JobDict
from src.utils.normalizer import normalize_location

logger = logging.getLogger(__name__)

# ?content=true is required — omitting it causes the API to return jobs without the 'content' (description) field
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
        JSON decode errors and unexpected payload shapes are also logged and skipped per-token.

        Returns:
            Flat list of raw job dicts from all successful API responses.
        """
        board_tokens: dict[str, str] = self.config.get("greenhouse_board_tokens") or {}
        if not board_tokens:
            logger.warning("GreenhouseCrawler: no board tokens configured — skipping fetch")
            return []
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

        Required fields: title, id, absolute_url, _company_name.
        Returns None (and logs the reason) if any required field is absent.
        location, description, and date_posted are optional and may be None.
        Never logs raw record content — logs the skip reason only (DECISIONS.md).

        Args:
            item: Single raw job dict from the Greenhouse API response.

        Returns:
            Populated JobDict on success, None on validation failure.
        """
        if not isinstance(item, dict):
            logger.warning("GreenhouseCrawler: skipping job — expected dict, got %s", type(item).__name__)
            return None

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
            logger.warning(
                "GreenhouseCrawler: skipping job — '_company_name' not injected (record was not produced by fetch())"
            )
            return None

        # location is a nested dict in the Greenhouse response; guard against non-dict values
        location_obj = item.get("location")
        location_raw = (
            location_obj["name"]
            if isinstance(location_obj, dict) and location_obj.get("name")
            else None
        )
        location_normalized = normalize_location(location_raw, self.config.get("location_aliases"))

        # Greenhouse does not expose a dedicated date_posted field in the list endpoint.
        # updated_at is used as the closest available approximation.
        date_posted = item.get("updated_at") or None  # coerce empty string to None

        # 'content' is present only because _BASE_URL includes ?content=true
        description = _strip_html(item.get("content"))

        return JobDict(
            title=str(title),
            company=str(company),
            source_url=str(absolute_url),
            ats_job_id=str(job_id),
            location=location_raw,
            location_normalized=location_normalized,
            description=description,
            date_posted=date_posted,
            source_name="greenhouse",
        )


def _strip_html(html: str | None) -> str | None:
    """Convert an HTML string to plain text. Returns None for empty or absent input.

    Uses BeautifulSoup with the built-in html.parser. Separates block-level
    elements with a space so words do not run together after tag removal.

    Args:
        html: Raw HTML string from the Greenhouse API content field, or None.

    Returns:
        Plain-text string with leading/trailing whitespace stripped,
        or None if the input is absent or results in an empty string.
    """
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
    return text if text else None
