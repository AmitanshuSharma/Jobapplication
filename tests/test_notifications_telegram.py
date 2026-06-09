"""Tests for src/notifications/telegram_notifier.py."""
import json

import pytest
import requests
from unittest.mock import MagicMock, patch

from src.notifications.telegram_notifier import send_telegram

CONFIG = {
    "TELEGRAM_BOT_TOKEN": "secret-token-abc123",
    "TELEGRAM_CHAT_ID": "999888777",
}

JOB = {
    "title": "Senior Data Engineer",
    "company": "Stripe",
    "location_normalized": "Remote, India",
    "score": 27,
    "source_url": "https://example.com/job/1",
    "score_breakdown": json.dumps({
        "components": [
            {"label": "PySpark", "points": 10},
            {"label": "Presales", "points": -5},
        ],
        "role_match": True,
        "matched_positive_keywords": ["PySpark"],
        "matched_negative_keywords": ["Presales"],
        "final_score": 27,
        "threshold_at_ingestion": 20,
    }),
}


def _mock_response(status_code: int, ok: bool) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"ok": ok}
    return resp


def test_send_telegram_success():
    with patch("src.notifications.telegram_notifier.requests.post",
               return_value=_mock_response(200, True)):
        assert send_telegram(JOB, CONFIG) is True


def test_send_telegram_non_200_returns_false():
    with patch("src.notifications.telegram_notifier.requests.post",
               return_value=_mock_response(400, False)):
        assert send_telegram(JOB, CONFIG) is False


def test_send_telegram_200_ok_false_returns_false():
    with patch("src.notifications.telegram_notifier.requests.post",
               return_value=_mock_response(200, False)):
        assert send_telegram(JOB, CONFIG) is False


def test_send_telegram_network_error_returns_false():
    with patch("src.notifications.telegram_notifier.requests.post",
               side_effect=requests.RequestException("timeout")):
        assert send_telegram(JOB, CONFIG) is False


def test_token_not_in_log_output(caplog):
    with patch("src.notifications.telegram_notifier.requests.post",
               return_value=_mock_response(400, False)):
        with caplog.at_level("WARNING", logger="src.notifications.telegram_notifier"):
            send_telegram(JOB, CONFIG)
    assert "secret-token-abc123" not in caplog.text


def test_post_uses_html_parse_mode():
    with patch("src.notifications.telegram_notifier.requests.post",
               return_value=_mock_response(200, True)) as mock_post:
        send_telegram(JOB, CONFIG)
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["parse_mode"] == "HTML"


def test_post_sends_to_correct_chat_id():
    with patch("src.notifications.telegram_notifier.requests.post",
               return_value=_mock_response(200, True)) as mock_post:
        send_telegram(JOB, CONFIG)
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["chat_id"] == "999888777"


def test_message_includes_score_breakdown():
    with patch("src.notifications.telegram_notifier.requests.post",
               return_value=_mock_response(200, True)) as mock_post:
        send_telegram(JOB, CONFIG)
    _, kwargs = mock_post.call_args
    assert "+10 PySpark" in kwargs["json"]["text"]
    assert "-5 Presales" in kwargs["json"]["text"]
