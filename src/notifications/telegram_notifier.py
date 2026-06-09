"""Telegram transport for job notifications.

Inputs: job record dict, config dict.
Outputs: HTTP POST to Telegram Bot API. Returns bool.

Does not own: message formatting (delegated to formatters),
              database access, eligibility decisions.
"""
from __future__ import annotations

import logging

import requests

from src.notifications.formatters import format_telegram_message

logger = logging.getLogger(__name__)

_TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(job_record: dict, config: dict) -> bool:
    """Send a Telegram message for a job record.

    Args:
        job_record: Must have title, company, location_normalized,
                    score, score_breakdown, source_url.
        config: Must contain TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.

    Returns:
        True on HTTP 200 with ok=True, False on any failure. Never raises.
    """
    token = config.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = config.get("TELEGRAM_CHAT_ID", "")
    url = _TELEGRAM_API_URL.format(token=token)
    text = format_telegram_message(job_record)

    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if response.status_code == 200 and response.json().get("ok"):
            return True
        logger.warning(
            "Telegram send failed: status=%d channel=TELEGRAM",
            response.status_code,
        )
        return False
    except requests.RequestException as exc:
        logger.warning("Telegram send error: %s channel=TELEGRAM", str(exc))
        return False
