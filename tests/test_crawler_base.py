# tests/test_crawler_base.py
"""Tests for src/crawlers/base.py — BaseCrawler abstract contract and Model B isolation."""
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
                logger_name = self.__class__.__name__
                import logging
                logging.getLogger(__name__).warning(
                    "%s: skipping job — missing required field 'title'", logger_name
                )
                continue
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


def test_run_skips_record_missing_title():
    result = _ModelBCrawler({}).run()
    titles = [j["title"] for j in result]
    assert "Data Engineer" in titles
    assert "Analytics Engineer" in titles


def test_run_does_not_return_malformed_records():
    result = _ModelBCrawler({}).run()
    for job in result:
        assert job.get("title")


# --- Config storage ---

def test_config_stored_on_instance():
    config = {"notification_threshold": 20, "accepted_locations": ["Remote"]}
    crawler = _WorkingCrawler(config)
    assert crawler.config == config


def test_empty_config_accepted():
    crawler = _WorkingCrawler({})
    assert crawler.config == {}
