"""Email transport for job notifications.

Inputs: job record dict, config dict.
Outputs: SMTP email. Returns bool.

Does not own: message formatting (delegated to formatters),
              database access, eligibility decisions.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.notifications.formatters import format_email_body, format_email_subject

logger = logging.getLogger(__name__)


def send_email(job_record: dict, config: dict) -> bool:
    """Send an email notification for a job record.

    Args:
        job_record: Must have title, company, location_normalized,
                    score, score_breakdown, source_url.
        config: Must contain EMAIL_ADDRESS, EMAIL_PASSWORD, SMTP_HOST, SMTP_PORT.

    Returns:
        True on successful send, False on any failure. Never raises.
    """
    address = config.get("EMAIL_ADDRESS", "")
    password = config.get("EMAIL_PASSWORD", "")
    host = config.get("SMTP_HOST", "")
    port = int(config.get("SMTP_PORT", 587))

    subject = format_email_subject(job_record)
    body = format_email_body(job_record)

    msg = MIMEMultipart()
    msg["From"] = address
    msg["To"] = address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(address, password)
            server.sendmail(address, address, msg.as_string())
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Email send failed: %s channel=EMAIL", str(exc))
        return False
