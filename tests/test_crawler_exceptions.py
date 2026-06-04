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


def test_crawler_parse_error_url_defaults_to_empty_string():
    exc = CrawlerParseError("missing field")
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


def test_both_errors_are_subclasses_of_exception():
    assert issubclass(CrawlerFetchError, Exception)
    assert issubclass(CrawlerParseError, Exception)
