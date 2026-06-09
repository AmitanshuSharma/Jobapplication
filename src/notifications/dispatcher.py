"""Notification dispatcher for the Job Intelligence Platform.

Inputs: config dict, sqlite3.Connection (caller owns lifecycle).
Outputs: sends Telegram + email for eligible jobs; calls mark_notified on success.

Ownership:
- dispatcher owns: eligibility query, channel invocation, success policy, mark_notified.
- Transport modules (telegram_notifier, email_notifier) own delivery.
- Connection lifecycle is owned by the caller.

Forbidden imports enforced: no sqlite3 at runtime — from __future__ annotations
makes the sqlite3.Connection type hint a lazy string, so no runtime import needed.
No crawlers, no dashboard, no scoring.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.db.jobs_repository import get_notification_candidates, mark_notified
from src.notifications.email_notifier import send_email
from src.notifications.telegram_notifier import send_telegram

logger = logging.getLogger(__name__)


def dispatch_new_jobs(config: dict, conn: sqlite3.Connection) -> dict:
    """Query and notify eligible jobs; mark notified when at least one channel succeeds.

    Eligibility query (delegated to repository):
        notified=0 AND location_ineligible=0 AND score >= threshold.

    Success policy: at least one of [Telegram, Email] returns True → mark_notified.
    Both channels are always attempted independently regardless of each other's result.

    Args:
        config: Full config dict. Needs notification_threshold plus transport credentials.
        conn: Open SQLite connection. Caller owns lifecycle; dispatcher never closes it.

    Returns:
        {"eligible": int, "attempted": int, "notified": int, "both_failed": int}
    """
    threshold = int(config.get("notification_threshold", 20))
    candidates = get_notification_candidates(threshold, conn)

    eligible = len(candidates)
    attempted = 0
    notified = 0
    both_failed = 0

    for job in candidates:
        attempted += 1
        tg_ok = send_telegram(job, config)
        em_ok = send_email(job, config)

        if tg_ok or em_ok:
            mark_notified(job["id"], conn)
            notified += 1
        else:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.warning(
                "Both channels failed job_id=%d at %s", job["id"], timestamp
            )
            both_failed += 1

    return {
        "eligible": eligible,
        "attempted": attempted,
        "notified": notified,
        "both_failed": both_failed,
    }
