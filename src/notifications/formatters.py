"""Message formatters for job notifications.

Inputs: job record dict (fields: title, company, location_normalized, score,
        score_breakdown (JSON string), source_url).
Outputs: formatted strings for Telegram (HTML) and email (plain text).

Owns: format_telegram_message, format_email_subject, format_email_body.
Does not own: delivery, config loading, database access.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _render_components(score_breakdown_json: str | None) -> str:
    """Parse score_breakdown JSON and render one line per component.

    Positive points: "+10 PySpark". Negative points: "-5 Presales".
    """
    if score_breakdown_json is None:
        return "(breakdown unavailable)"
    try:
        breakdown = json.loads(score_breakdown_json)
        components = breakdown.get("components", [])
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse score_breakdown; omitting from message")
        return "(breakdown unavailable)"

    if not components:
        return "(no components)"

    lines = []
    for c in components:
        pts = c.get("points", 0)
        label = c.get("label", "")
        prefix = f"+{pts}" if pts > 0 else str(pts)
        lines.append(f"{prefix} {label}")
    return "\n".join(lines)


def format_telegram_message(job_record: dict) -> str:
    """Return an HTML-formatted Telegram message for a job record."""
    title = job_record.get("title", "")
    company = job_record.get("company", "")
    location = job_record.get("location_normalized") or job_record.get("location", "")
    score = job_record.get("score", 0)
    source_url = job_record.get("source_url", "")
    breakdown = _render_components(job_record.get("score_breakdown"))

    return (
        "<b>Job Alert</b>\n\n"
        f"<b>Title:</b> {title}\n"
        f"<b>Company:</b> {company}\n"
        f"<b>Location:</b> {location}\n"
        f"<b>Score:</b> {score}\n\n"
        f"<b>Score Breakdown:</b>\n{breakdown}\n\n"
        f'<a href="{source_url}">View Job</a>'
    )


def format_email_subject(job_record: dict) -> str:
    """Return the email subject line for a job record."""
    title = job_record.get("title", "")
    company = job_record.get("company", "")
    score = job_record.get("score", 0)
    return f"[Job Alert] {title} — {company} (Score: {score})"


def format_email_body(job_record: dict) -> str:
    """Return a plain-text email body for a job record."""
    title = job_record.get("title", "")
    company = job_record.get("company", "")
    location = job_record.get("location_normalized") or job_record.get("location", "")
    score = job_record.get("score", 0)
    source_url = job_record.get("source_url", "")
    breakdown = _render_components(job_record.get("score_breakdown"))

    return (
        "Job Alert\n\n"
        f"Title:    {title}\n"
        f"Company:  {company}\n"
        f"Location: {location}\n"
        f"Score:    {score}\n\n"
        f"Score Breakdown:\n{breakdown}\n\n"
        f"Link: {source_url}"
    )
