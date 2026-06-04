# tests/test_crawler_workday_http.py
"""Tests for src/crawlers/workday_http.py — all HTTP calls mocked."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.crawlers.exceptions import CrawlerFetchError
from src.crawlers.workday_http import post


def _make_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    return resp


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_successful_200_returns_response(mock_post, mock_sleep):
    mock_post.return_value = _make_response(200)
    result = post("https://example.com/api", json_payload={"k": "v"}, max_retries=1, rate_limit_delay=0)
    assert result.status_code == 200


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_non_retryable_403_raises_without_retry(mock_post, mock_sleep):
    mock_post.return_value = _make_response(403)
    with pytest.raises(CrawlerFetchError):
        post("https://example.com/api", max_retries=3, rate_limit_delay=0)
    assert mock_post.call_count == 1


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_non_retryable_404_raises_without_retry(mock_post, mock_sleep):
    mock_post.return_value = _make_response(404)
    with pytest.raises(CrawlerFetchError):
        post("https://example.com/api", max_retries=3, rate_limit_delay=0)
    assert mock_post.call_count == 1


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_500_retried_succeeds_on_second_attempt(mock_post, mock_sleep):
    mock_post.side_effect = [_make_response(500), _make_response(200)]
    result = post("https://example.com/api", max_retries=2, rate_limit_delay=0)
    assert result.status_code == 200
    assert mock_post.call_count == 2


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_500_all_retries_exhausted_raises(mock_post, mock_sleep):
    mock_post.return_value = _make_response(500)
    with pytest.raises(CrawlerFetchError):
        post("https://example.com/api", max_retries=3, rate_limit_delay=0)
    assert mock_post.call_count == 3


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_429_is_retried(mock_post, mock_sleep):
    mock_post.side_effect = [_make_response(429), _make_response(200)]
    result = post("https://example.com/api", max_retries=2, rate_limit_delay=0)
    assert result.status_code == 200


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_sends_json_payload_in_body(mock_post, mock_sleep):
    mock_post.return_value = _make_response(200)
    post("https://example.com/api", json_payload={"limit": 20, "offset": 0}, max_retries=1, rate_limit_delay=0)
    assert mock_post.call_args.kwargs.get("json") == {"limit": 20, "offset": 0}


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_error_carries_url(mock_post, mock_sleep):
    mock_post.return_value = _make_response(404)
    with pytest.raises(CrawlerFetchError) as exc_info:
        post("https://api.example.com/jobs", max_retries=1, rate_limit_delay=0)
    assert exc_info.value.url == "https://api.example.com/jobs"


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_connection_error_raises(mock_post, mock_sleep):
    mock_post.side_effect = requests.ConnectionError("refused")
    with pytest.raises(CrawlerFetchError):
        post("https://example.com/api", max_retries=1, rate_limit_delay=0)


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_connection_error_succeeds_on_retry(mock_post, mock_sleep):
    mock_post.side_effect = [requests.ConnectionError("refused"), _make_response(200)]
    result = post("https://example.com/api", max_retries=2, rate_limit_delay=0)
    assert result.status_code == 200


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_rate_limit_delay_applied_before_first_request(mock_post, mock_sleep):
    mock_post.return_value = _make_response(200)
    post("https://example.com/api", max_retries=1, rate_limit_delay=1.5)
    mock_sleep.assert_any_call(1.5)


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_backoff_capped_at_16s(mock_post, mock_sleep):
    mock_post.return_value = _make_response(500)
    with pytest.raises(CrawlerFetchError):
        post("https://example.com/api", max_retries=7, rate_limit_delay=0)
    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
    assert all(s <= 16 for s in sleep_calls)


@patch("src.crawlers.workday_http.time.sleep")
@patch("src.crawlers.workday_http.requests.post")
def test_zero_retries_raises_without_making_request(mock_post, mock_sleep):
    """max_retries=0 raises immediately without making any HTTP request."""
    with pytest.raises(CrawlerFetchError):
        post("https://example.com/api", max_retries=0, rate_limit_delay=0)
    mock_post.assert_not_called()
