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

            # Lever returns a flat JSON array, not a nested dict like Greenhouse
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
