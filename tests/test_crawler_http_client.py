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
    mock_get.return_value = _make_response(500)
    with pytest.raises(CrawlerFetchError):
        get("https://example.com", max_retries=7, rate_limit_delay=0)
    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
    assert all(s <= 16 for s in sleep_calls)


@patch("src.crawlers.http_client.time.sleep")
@patch("src.crawlers.http_client.requests.get")
def test_headers_passed_through(mock_get, mock_sleep):
    mock_get.return_value = _make_response(200)
    headers = {"User-Agent": "TestBot/1.0"}
    get("https://example.com", headers=headers, max_retries=1, rate_limit_delay=0)
    _, kwargs = mock_get.call_args
    assert kwargs.get("headers") == headers
