# src/crawlers/playwright_utils.py
"""Playwright-based page renderer for JavaScript-rendered sources.

Inputs:  url string, optional timeout_ms.
Outputs: rendered HTML string.
No database access. No scoring. No notifications. No direct HTTP.
"""
from __future__ import annotations

import logging

from src.crawlers.exceptions import CrawlerFetchError

logger = logging.getLogger(__name__)


def render_page(url: str, timeout_ms: int = 30000) -> str:
    """Launch headless Chromium, load url, wait for JS to settle, return HTML.

    Args:
        url: URL to render.
        timeout_ms: Navigation timeout in milliseconds.

    Returns:
        Rendered HTML string.

    Raises:
        CrawlerFetchError: If the page cannot be loaded or times out.
    """
    # Import inline so the module stays importable if playwright is not installed
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
    except ImportError as exc:
        raise CrawlerFetchError(f"playwright is not installed: {exc}", url=url)

    logger.info("Playwright: rendering %s", url)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                html = page.content()
            finally:
                browser.close()
            return html
    except PlaywrightTimeout as exc:
        raise CrawlerFetchError(f"Playwright timeout loading {url}: {exc}", url=url)
    except Exception as exc:
        raise CrawlerFetchError(f"Playwright failed to load {url}: {exc}", url=url)
