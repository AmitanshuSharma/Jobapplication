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

    parse() implementations must follow Model B (per-record isolation):
    - Skip malformed individual records and log: "{CrawlerName}: skipping job — {reason}"
    - Return all valid records from the same payload
    - Raise CrawlerParseError only for structural failures (entire payload unusable)
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
