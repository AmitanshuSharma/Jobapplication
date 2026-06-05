# src/crawlers/workday.py
"""Workday career page crawler.

Primary strategy: POST to Workday CXS JSON API (no JS rendering needed).
Fallback strategy: Playwright + BeautifulSoup HTML parsing when CXS is unavailable.

Inputs: config dict — workday_urls ({display_name: url} dict), request settings, location_aliases.
Outputs: list[JobDict] from run() — one entry per valid open role found.
No database access. No scoring. No notifications.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.crawlers import playwright_utils
from src.crawlers import workday_http
from src.crawlers.base import BaseCrawler
from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.models import JobDict
from src.utils.normalizer import normalize_location

logger = logging.getLogger(__name__)

_CXS_PATH = "/wday/cxs/{tenant}/{site_name}/jobs"
_CXS_LIMIT = 20
# Matches locale codes like en-US, fr-FR
_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def _parse_workday_url(url: str) -> tuple[str, str, str]:
    """Extract (base_url, tenant, site_name) from a Workday career page URL.

    base_url  = scheme + hostname (no path).
    tenant    = first subdomain segment (e.g. 'atlassian' from atlassian.wd5.myworkdayjobs.com).
    site_name = first non-locale path segment (e.g. 'Atlassian' from /en-US/Atlassian).

    Args:
        url: Workday career page URL from config.

    Returns:
        Tuple of (base_url, tenant, site_name).

    Raises:
        ValueError: If url is not a Workday URL or site_name cannot be extracted.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if "myworkdayjobs.com" not in hostname:
        raise ValueError(f"Not a Workday URL: {url}")

    parts = hostname.split(".")
    if len(parts) < 3:
        raise ValueError(f"Cannot extract tenant from hostname: {hostname}")
    tenant = parts[0]

    path_segments = [p for p in parsed.path.split("/") if p]
    non_locale = [p for p in path_segments if not _LOCALE_RE.match(p)]
    if not non_locale:
        raise ValueError(f"Cannot extract site_name from path: {parsed.path!r}")
    site_name = non_locale[0]

    base_url = f"{parsed.scheme}://{hostname}"
    return base_url, tenant, site_name


class WorkdayCrawler(BaseCrawler):
    """Fetches open roles from Workday-hosted career pages.

    For each configured URL: tries CXS JSON API POST first; falls back to Playwright
    HTML rendering if CXS fails. Each URL is independent — one failure does not
    affect others.

    Config keys:
        workday_urls (dict): {display_name: url} pairs.
            display_name is used as the 'company' field in emitted JobDicts.
            url is the career page URL, e.g. https://{tenant}.wd5.myworkdayjobs.com/en-US/{site}.
        request_timeout_seconds (int): HTTP timeout in seconds. Default 30.
        max_retries (int): Retry attempts per request. Default 3.
        user_agent (str): User-Agent header value.
        location_aliases (dict): Passed to normalize_location(). Optional.
    """

    def fetch(self) -> list[dict]:
        """Fetch raw job data from all configured Workday URLs.

        For each (name, url) pair: tries CXS JSON POST first; falls back to Playwright
        on failure. Each URL produces one tagged dict. URLs that fail both strategies
        are skipped; others continue.

        Returns:
            List of per-URL raw dicts. Each dict has:
              _strategy: "json" or "html"
              _company_name: display name from config
              _configured_url: original URL from config
              job_postings (if json): list of CXS job dicts
              html (if html): rendered HTML string
        """
        workday_urls: dict[str, str] = self.config.get("workday_urls") or {}
        if not workday_urls:
            logger.warning("WorkdayCrawler: no Workday URLs configured — skipping fetch")
            return []

        results: list[dict] = []
        for company_name, url in workday_urls.items():
            raw_item = self._fetch_one_url(company_name, url)
            if raw_item is not None:
                results.append(raw_item)
        return results

    def _fetch_one_url(self, company_name: str, url: str) -> dict | None:
        """Fetch a single Workday URL. Returns a tagged raw dict, or None if both strategies fail."""
        try:
            base_url, tenant, site_name = _parse_workday_url(url)
        except ValueError as exc:
            logger.error("WorkdayCrawler: cannot parse URL %s — %s", url, exc)
            return None

        # Strategy 1: CXS JSON API (no browser required)
        cxs_url = f"{base_url}{_CXS_PATH.format(tenant=tenant, site_name=site_name)}"
        try:
            job_postings = self._fetch_cxs(cxs_url)
            logger.info(
                "WorkdayCrawler: CXS strategy succeeded for %s (%d jobs)", url, len(job_postings)
            )
            return {
                "_strategy": "json",
                "_company_name": company_name,
                "_configured_url": url,
                "job_postings": job_postings,
            }
        except CrawlerFetchError as exc:
            logger.warning(
                "WorkdayCrawler: CXS failed for %s (%s) — falling back to Playwright", url, exc
            )

        # Strategy 2: Playwright fallback
        try:
            html = playwright_utils.render_page(url)
            logger.info("WorkdayCrawler: Playwright fallback succeeded for %s", url)
            return {
                "_strategy": "html",
                "_company_name": company_name,
                "_configured_url": url,
                "html": html,
            }
        except CrawlerFetchError as exc:
            logger.error("WorkdayCrawler: both strategies failed for %s — %s", url, exc)
            return None

    def _fetch_cxs(self, cxs_url: str) -> list[dict]:
        """POST to the Workday CXS API and return all job_postings across pages.

        Raises CrawlerFetchError on first-page failure (triggers Playwright fallback).
        On subsequent page failures, logs a warning and returns what was fetched so far
        rather than raising — preserving partial results is better than losing them.

        Args:
            cxs_url: Full CXS endpoint URL.

        Returns:
            Flat list of raw CXS job posting dicts.

        Raises:
            CrawlerFetchError: If the first page POST fails or has unexpected structure.
        """
        all_jobs: list[dict] = []
        offset = 0
        first_page = True

        while True:
            payload = {
                "limit": _CXS_LIMIT,
                "offset": offset,
                "searchText": "",
                "appliedFacets": {},
            }
            try:
                response = workday_http.post(
                    cxs_url,
                    json_payload=payload,
                    headers={
                        "User-Agent": self.config.get("user_agent", "JobIntelligencePlatform/1.0"),
                        "Content-Type": "application/json",
                    },
                    timeout=self.config.get("request_timeout_seconds", 30),
                    max_retries=self.config.get("max_retries", 3),
                )
            except CrawlerFetchError as exc:
                if first_page:
                    raise
                # Partial results from previous pages are preserved
                logger.warning(
                    "WorkdayCrawler: pagination failed at offset %d (%s) — returning %d jobs fetched so far",
                    offset,
                    exc,
                    len(all_jobs),
                )
                break

            try:
                data = response.json()
            except Exception as exc:
                if first_page:
                    raise CrawlerFetchError(
                        f"CXS response is not valid JSON: {exc}", url=cxs_url
                    ) from exc
                logger.warning(
                    "WorkdayCrawler: CXS page at offset %d has invalid JSON for %s — returning %d jobs so far",
                    offset, cxs_url, len(all_jobs),
                )
                break

            if not isinstance(data, dict) or "jobPostings" not in data:
                if first_page:
                    raise CrawlerFetchError(
                        f"CXS response missing 'jobPostings' key — got: "
                        f"{list(data.keys()) if isinstance(data, dict) else type(data).__name__}",
                        url=cxs_url,
                    )
                logger.warning(
                    "WorkdayCrawler: CXS page at offset %d missing 'jobPostings' for %s — returning %d jobs so far",
                    offset, cxs_url, len(all_jobs),
                )
                break

            page_jobs = data["jobPostings"]
            if not isinstance(page_jobs, list):
                if first_page:
                    raise CrawlerFetchError(
                        f"CXS 'jobPostings' is not a list — got {type(page_jobs).__name__}",
                        url=cxs_url,
                    )
                logger.warning(
                    "WorkdayCrawler: CXS 'jobPostings' is not a list at offset %d for %s — returning %d jobs so far",
                    offset, cxs_url, len(all_jobs),
                )
                break

            all_jobs.extend(page_jobs)
            first_page = False

            total = data.get("total", 0)
            offset += _CXS_LIMIT
            if offset >= total:
                break

        return all_jobs

    def parse(self, raw: list[dict]) -> list[JobDict]:
        """Parse per-URL raw items into a flat list of JobDicts.

        Dispatches to JSON or HTML parsing based on '_strategy'.
        Model B: skips malformed records, returns valid ones.
        Raises CrawlerParseError only if raw is not a list (structural failure).

        Args:
            raw: List of per-URL dicts as returned by fetch().

        Returns:
            Flat list of valid JobDict objects.

        Raises:
            CrawlerParseError: If raw is not a list.
        """
        if not isinstance(raw, list):
            raise CrawlerParseError(
                f"WorkdayCrawler: expected list from fetch(), got {type(raw).__name__}"
            )

        results: list[JobDict] = []
        for item in raw:
            if not isinstance(item, dict):
                logger.warning("WorkdayCrawler: skipping raw item — not a dict")
                continue

            strategy = item.get("_strategy")
            company_name = item.get("_company_name", "unknown")
            configured_url = item.get("_configured_url", "")

            if strategy == "json":
                results.extend(
                    self._parse_json_items(
                        item.get("job_postings", []), company_name, configured_url
                    )
                )
            elif strategy == "html":
                results.extend(
                    self._parse_html_items(item.get("html", ""), company_name, configured_url)
                )
            else:
                logger.warning(
                    "WorkdayCrawler: skipping raw item — unknown strategy %r", strategy
                )

        return results

    def _parse_json_items(
        self, job_postings: list[dict], company_name: str, configured_url: str
    ) -> list[JobDict]:
        """Apply _parse_one_json to each CXS posting; collect non-None results (Model B)."""
        results = []
        for item in job_postings:
            job = self._parse_one_json(item, company_name, configured_url)
            if job is not None:
                results.append(job)
        return results

    def _parse_one_json(
        self, item: dict, company_name: str, configured_url: str
    ) -> JobDict | None:
        """Map a single CXS job posting dict to a JobDict.

        Required fields: title, externalPath. All others are optional.
        Returns None and logs skip reason if any required field is absent.

        Args:
            item: Single raw CXS job posting dict.
            company_name: Human-readable display name from config (not the tenant slug).
            configured_url: Original career page URL from config (used to build source_url).

        Returns:
            Populated JobDict on success, None on validation failure.
        """
        if not isinstance(item, dict):
            logger.warning(
                "WorkdayCrawler: skipping CXS job — expected dict, got %s", type(item).__name__
            )
            return None

        title = item.get("title")
        if not title:
            logger.warning("WorkdayCrawler: skipping CXS job — missing required field 'title'")
            return None

        external_path = item.get("externalPath")
        if not external_path:
            logger.warning(
                "WorkdayCrawler: skipping CXS job — missing required field 'externalPath'"
            )
            return None

        # source_url: configured URL (includes locale/site path) + the job-specific path suffix
        source_url = configured_url.rstrip("/") + external_path
        ats_job_id = item.get("jobReqId") or None
        location_raw = item.get("locationsText") or None
        location_normalized = normalize_location(location_raw, self.config.get("location_aliases"))
        date_posted = item.get("postedOn") or None

        return JobDict(
            title=str(title),
            company=str(company_name),
            source_url=str(source_url),
            ats_job_id=str(ats_job_id) if ats_job_id else None,
            location=location_raw,
            location_normalized=location_normalized,
            description=None,
            date_posted=date_posted,
            source_name="workday",
        )

    def _parse_html_items(
        self, html: str, company_name: str, configured_url: str
    ) -> list[JobDict]:
        """Parse Playwright-rendered Workday HTML into JobDicts.

        Uses data-automation-id attributes observed in Workday-hosted career pages.
        These attributes have been seen across multiple Workday tenants but are not
        part of a public API contract — they may change with Workday platform updates.
        If this method starts returning zero results, verify the current HTML structure
        before updating selectors.

        Observed on: atlassian.wd5, adobe.wd5 (verified 2024).

        Raises CrawlerParseError if no job link elements are found (structural failure).
        """
        soup = BeautifulSoup(html, "html.parser")
        job_links = soup.find_all("a", attrs={"data-automation-id": "jobPostingTitleLink"})

        if not job_links:
            raise CrawlerParseError(
                f"WorkdayCrawler: no job listings found in HTML for {configured_url} "
                f"— selector data-automation-id='jobPostingTitleLink' matched 0 elements"
            )

        results = []
        for link in job_links:
            job = self._parse_one_html(link, company_name, configured_url)
            if job is not None:
                results.append(job)
        return results

    def _parse_one_html(self, link_tag, company_name: str, configured_url: str) -> JobDict | None:
        """Parse a single Workday job anchor tag into a JobDict.

        Navigates up to the nearest li/div container to find sibling metadata elements.

        Args:
            link_tag: BeautifulSoup Tag — a jobPostingTitleLink anchor element.
            company_name: Human-readable display name from config (not the tenant slug).
            configured_url: Original career page URL from config.

        Returns:
            Populated JobDict on success, None on validation failure.
        """
        title = link_tag.get_text(strip=True)
        if not title:
            logger.warning("WorkdayCrawler: skipping HTML job — empty title in anchor tag")
            return None

        href = link_tag.get("href", "")
        if not href:
            logger.warning("WorkdayCrawler: skipping HTML job '%s' — missing href", title)
            return None

        if href.startswith("http"):
            source_url = href
        else:
            parsed_base = urlparse(configured_url)
            source_url = f"{parsed_base.scheme}://{parsed_base.hostname}{href}"

        container = link_tag.find_parent("li") or link_tag.find_parent("div")

        location_raw = None
        ats_job_id = None
        date_posted = None

        if container:
            loc_el = container.find(attrs={"data-automation-id": "locations"})
            if loc_el:
                location_raw = loc_el.get_text(strip=True) or None

            req_el = container.find(attrs={"data-automation-id": "jobRequisitionId"})
            if req_el:
                ats_job_id = req_el.get_text(strip=True) or None

            date_el = container.find(attrs={"data-automation-id": "postedOn"})
            if date_el:
                date_posted = date_el.get_text(strip=True) or None

        location_normalized = normalize_location(location_raw, self.config.get("location_aliases"))

        return JobDict(
            title=title,
            company=str(company_name),
            source_url=source_url,
            ats_job_id=ats_job_id,
            location=location_raw,
            location_normalized=location_normalized,
            description=None,
            date_posted=date_posted,
            source_name="workday",
        )
