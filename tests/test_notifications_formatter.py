"""Tests for src/notifications/formatters.py."""
import json

from src.notifications.formatters import (
    format_email_body,
    format_email_subject,
    format_telegram_message,
)

_BREAKDOWN = json.dumps({
    "role_match": True,
    "matched_positive_keywords": ["PySpark", "Databricks"],
    "matched_negative_keywords": ["Presales"],
    "components": [
        {"label": "PySpark", "points": 10},
        {"label": "Databricks", "points": 10},
        {"label": "Kafka", "points": 8},
        {"label": "Presales", "points": -5},
    ],
    "final_score": 27,
    "threshold_at_ingestion": 20,
})

JOB = {
    "title": "Senior Data Engineer",
    "company": "Stripe",
    "location_normalized": "Remote, India",
    "score": 27,
    "source_url": "https://boards.greenhouse.io/stripe/jobs/123",
    "score_breakdown": _BREAKDOWN,
}


# --- format_telegram_message ---

def test_telegram_contains_title():
    assert "Senior Data Engineer" in format_telegram_message(JOB)


def test_telegram_contains_company():
    assert "Stripe" in format_telegram_message(JOB)


def test_telegram_contains_location():
    assert "Remote, India" in format_telegram_message(JOB)


def test_telegram_contains_score():
    assert "27" in format_telegram_message(JOB)


def test_telegram_contains_source_url():
    assert "https://boards.greenhouse.io/stripe/jobs/123" in format_telegram_message(JOB)


def test_telegram_uses_html_bold_tags():
    assert "<b>" in format_telegram_message(JOB)


def test_telegram_positive_component_format():
    assert "+10 PySpark" in format_telegram_message(JOB)


def test_telegram_negative_component_format():
    assert "-5 Presales" in format_telegram_message(JOB)


def test_telegram_all_components_present():
    msg = format_telegram_message(JOB)
    assert "+10 Databricks" in msg
    assert "+8 Kafka" in msg


def test_telegram_missing_breakdown_renders_gracefully():
    job = {**JOB, "score_breakdown": None}
    msg = format_telegram_message(job)
    assert "breakdown unavailable" in msg


def test_telegram_empty_components_renders_gracefully():
    job = {**JOB, "score_breakdown": json.dumps({"components": []})}
    msg = format_telegram_message(job)
    assert "no components" in msg


# --- format_email_subject ---

def test_email_subject_exact_format():
    subject = format_email_subject(JOB)
    assert subject == "[Job Alert] Senior Data Engineer — Stripe (Score: 27)"


def test_email_subject_contains_title():
    assert "Senior Data Engineer" in format_email_subject(JOB)


def test_email_subject_contains_score():
    assert "27" in format_email_subject(JOB)


# --- format_email_body ---

def test_email_body_contains_title():
    assert "Senior Data Engineer" in format_email_body(JOB)


def test_email_body_contains_company():
    assert "Stripe" in format_email_body(JOB)


def test_email_body_contains_location():
    assert "Remote, India" in format_email_body(JOB)


def test_email_body_contains_source_url():
    assert "https://boards.greenhouse.io/stripe/jobs/123" in format_email_body(JOB)


def test_email_body_positive_component_format():
    assert "+10 PySpark" in format_email_body(JOB)


def test_email_body_negative_component_format():
    assert "-5 Presales" in format_email_body(JOB)


def test_email_body_no_html_tags():
    body = format_email_body(JOB)
    assert "<b>" not in body
    assert "</b>" not in body
