"""Ingestion pipeline for the Job Intelligence Platform.

Inputs: list of job dicts from any crawler's run(), config dict, sqlite3.Connection.
Outputs: inserts new jobs via jobs_repository; returns summary dict.

Ownership rules enforced here:
- Caller owns connection lifecycle (ingest never opens or closes conn).
- ingest owns dedup_hash generation.
- Location eligibility uses canonical exact match.
- No notification logic.
- Repository exceptions propagate without suppression.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone

from src.db.jobs_repository import insert_job, job_exists_by_dedup_key
from src.scoring.scorer import score_job
from src.utils.normalizer import normalize_location

logger = logging.getLogger(__name__)


def _compute_dedup_hash(company: str, title: str, location_normalized: "str | None") -> str:
    """SHA-256 of normalised company+title+location. Owned by ingest, not repository."""
    raw = (
        company.lower().strip()
        + title.lower().strip()
        + (location_normalized or "").lower().strip()
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def ingest_jobs(jobs: list[dict], config: dict, conn: "sqlite3.Connection") -> dict:
    """Ingest a list of job dicts, dedup, score, and persist via the repository.

    Args:
        jobs: Raw job dicts produced by any crawler's run().
        config: Application config dict (accepted_locations, location_aliases, …).
        conn: Open SQLite connection. Caller owns the lifecycle; ingest never closes it.

    Returns:
        Summary dict with keys: processed, inserted, skipped_duplicate, rejected,
        location_ineligible.
    """
    summary = {
        "processed": 0,
        "inserted": 0,
        "skipped_duplicate": 0,
        "rejected": 0,
        "location_ineligible": 0,
    }

    accepted_locations: list[str] = config.get("accepted_locations", [])
    location_aliases: dict = config.get("location_aliases", {})

    for job in jobs:
        summary["processed"] += 1

        # 1. Validate required fields.
        title = job.get("title")
        company = job.get("company")
        source_url = job.get("source_url")

        if not (title and isinstance(title, str) and title.strip()):
            logger.warning(
                "Job rejected — missing or empty 'title'. company=%r url=%r",
                company,
                source_url,
            )
            summary["rejected"] += 1
            continue

        if not (company and isinstance(company, str) and company.strip()):
            logger.warning(
                "Job rejected — missing or empty 'company'. title=%r url=%r",
                title,
                source_url,
            )
            summary["rejected"] += 1
            continue

        if not (source_url and isinstance(source_url, str) and source_url.strip()):
            logger.warning(
                "Job rejected — missing or empty 'source_url'. title=%r company=%r",
                title,
                company,
            )
            summary["rejected"] += 1
            continue

        # 2. Normalize location.
        location_normalized = normalize_location(job.get("location"), location_aliases)

        # 3. Location eligibility — exact canonical match only.
        if location_normalized is None:
            location_ineligible = 1
        elif any(
            accepted.lower() == location_normalized.lower()
            for accepted in accepted_locations
        ):
            location_ineligible = 0
        else:
            location_ineligible = 1

        # 4. Compute dedup key.
        ats_job_id = job.get("ats_job_id") or None
        if ats_job_id is not None:
            dedup_hash = None
        else:
            dedup_hash = _compute_dedup_hash(company, title, location_normalized)

        # 5. Dedup check.
        if job_exists_by_dedup_key(source_url, ats_job_id, dedup_hash, conn):
            logger.info(
                "Duplicate skipped. title=%r company=%r url=%r",
                title,
                company,
                source_url,
            )
            summary["skipped_duplicate"] += 1
            continue

        # 6. Score.
        score_result = score_job({**job, "location_normalized": location_normalized}, config)

        # 7. Build record.
        first_seen_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = {
            "source_url": job["source_url"],
            "ats_job_id": ats_job_id,
            "dedup_hash": dedup_hash,
            "title": job["title"],
            "company": job["company"],
            "location": job.get("location"),
            "location_normalized": location_normalized,
            "description": job.get("description"),
            "experience_range": job.get("experience_range"),
            "tech_stack": job.get("tech_stack"),
            "source_name": job.get("source_name"),
            "score": score_result["final_score"],
            "score_breakdown": json.dumps(score_result["score_breakdown"]),
            "passed_threshold": 1 if score_result["passed_threshold"] else 0,
            "status": "Pending",
            "tags": None,
            "notified": 0,
            "location_ineligible": location_ineligible,
            "first_seen_at": first_seen_at,
            "date_posted": job.get("date_posted"),
        }

        # 8. Insert — repository exceptions propagate.
        insert_job(record, conn)
        summary["inserted"] += 1
        if location_ineligible:
            summary["location_ineligible"] += 1

    return summary
