"""Tests for src/notifications/email_notifier.py."""
import json
import smtplib

import pytest
from unittest.mock import MagicMock, patch

from src.notifications.email_notifier import send_email

CONFIG = {
    "EMAIL_ADDRESS": "test@example.com",
    "EMAIL_PASSWORD": "s3cr3tp@ss",
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
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


def _patched_smtp():
    """Return a context-manager-compatible SMTP mock and the inner server mock."""
    mock_smtp_class = MagicMock()
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
    return mock_smtp_class, mock_server


def test_send_email_success():
    mock_smtp_class, mock_server = _patched_smtp()
    with patch("src.notifications.email_notifier.smtplib.SMTP", mock_smtp_class):
        result = send_email(JOB, CONFIG)
    assert result is True
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("test@example.com", "s3cr3tp@ss")
    mock_server.sendmail.assert_called_once()


def test_send_email_smtp_exception_returns_false():
    with patch("src.notifications.email_notifier.smtplib.SMTP") as MockSMTP:
        MockSMTP.side_effect = smtplib.SMTPException("auth failed")
        result = send_email(JOB, CONFIG)
    assert result is False


def test_send_email_os_error_returns_false():
    with patch("src.notifications.email_notifier.smtplib.SMTP") as MockSMTP:
        MockSMTP.side_effect = OSError("connection refused")
        result = send_email(JOB, CONFIG)
    assert result is False


def test_password_not_in_log_output(caplog):
    with patch("src.notifications.email_notifier.smtplib.SMTP") as MockSMTP:
        MockSMTP.side_effect = smtplib.SMTPException("fail")
        with caplog.at_level("WARNING", logger="src.notifications.email_notifier"):
            send_email(JOB, CONFIG)
    assert "s3cr3tp@ss" not in caplog.text


def test_format_subject_called_with_job():
    mock_smtp_class, _ = _patched_smtp()
    with patch("src.notifications.email_notifier.smtplib.SMTP", mock_smtp_class):
        with patch("src.notifications.email_notifier.format_email_subject",
                   return_value="[Job Alert] Senior Data Engineer — Stripe (Score: 27)") as mock_subj:
            send_email(JOB, CONFIG)
    mock_subj.assert_called_once_with(JOB)


def test_message_includes_score_breakdown():
    captured_body = []

    def fake_format_body(job_record):
        from src.notifications.formatters import format_email_body as real
        body = real(job_record)
        captured_body.append(body)
        return body

    mock_smtp_class, _ = _patched_smtp()
    with patch("src.notifications.email_notifier.smtplib.SMTP", mock_smtp_class):
        with patch("src.notifications.email_notifier.format_email_body",
                   side_effect=fake_format_body):
            send_email(JOB, CONFIG)

    assert captured_body, "format_email_body was never called"
    assert "+10 PySpark" in captured_body[0]
    assert "-5 Presales" in captured_body[0]


def test_smtp_port_cast_to_int():
    mock_smtp_class, _ = _patched_smtp()
    with patch("src.notifications.email_notifier.smtplib.SMTP", mock_smtp_class):
        send_email(JOB, CONFIG)
    args, _ = mock_smtp_class.call_args
    assert args[1] == 587  # int, not string "587"
