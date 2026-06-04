# src/crawlers/__init__.py
"""Crawler framework — public API."""
from src.crawlers.base import BaseCrawler
from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.models import JobDict

__all__ = ["BaseCrawler", "CrawlerFetchError", "CrawlerParseError", "JobDict"]
