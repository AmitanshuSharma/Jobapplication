"""Pipeline orchestrator for the Job Intelligence Platform.

Inputs: config dict.
Outputs: pipeline summary dict (see DECISIONS.md Pipeline Summary Format).

Owns: DB connection lifecycle, crawler invocation, ingestion, notification dispatch.
Does not own: crawling logic, scoring logic, notification transport, Streamlit.

Scheduler rule: all ingestion completes before notifications begin.
dispatch_new_jobs() is called exactly once per run, after every crawler batch
has been ingested.
"""
from __future__ import annotations

import logging

from src.crawlers.greenhouse import GreenhouseCrawler
from src.crawlers.lever import LeverCrawler
from src.crawlers.workday import WorkdayCrawler
from src.db.connection import get_connection
from src.notifications.dispatcher import dispatch_new_jobs
from src.pipeline.ingest import ingest_jobs

logger = logging.getLogger(__name__)

_ZERO_DISPATCH = {"eligible": 0, "attempted": 0, "notified": 0, "both_failed": 0}


def run_pipeline(config: dict) -> dict:
    """Run one complete pipeline cycle: crawl → ingest (per crawler) → dispatch.

    Opens one SQLite connection for the entire run and closes it in finally.

    Scheduler rule: all ingestion completes before dispatch_new_jobs is called.
    dispatch_new_jobs is called exactly once per run, after every crawler batch
    has been ingested.

    Args:
        config: Full config dict from config_loader. Must include database_path.

    Returns:
        Pipeline summary dict per DECISIONS.md:
        {
            "greenhouse_jobs":       int,
            "lever_jobs":            int,
            "workday_jobs":          int,
            "inserted_jobs":         int,
            "duplicate_jobs":        int,
            "rejected_jobs":         int,
            "notifications_sent":    int,
            "notification_failures": int,
            "dispatch_failed":       bool,
        }
    """
    logger.info("run_pipeline start")
    conn = get_connection(config["database_path"])

    # Built here (not at module level) so patches applied in tests take effect.
    crawlers = [
        ("greenhouse_jobs", "GreenhouseCrawler", GreenhouseCrawler),
        ("lever_jobs", "LeverCrawler", LeverCrawler),
        ("workday_jobs", "WorkdayCrawler", WorkdayCrawler),
    ]

    crawler_counts = {"greenhouse_jobs": 0, "lever_jobs": 0, "workday_jobs": 0}
    total_inserted = 0
    total_duplicates = 0
    total_rejected = 0
    dispatch_result = _ZERO_DISPATCH.copy()
    dispatch_failed = False

    try:
        for count_key, crawler_name, CrawlerClass in crawlers:
            logger.info("%s: starting", crawler_name)

            try:
                jobs = CrawlerClass(config).run()
            except Exception as exc:
                logger.error("%s: failed — %s", crawler_name, exc)
                continue

            crawler_counts[count_key] = len(jobs)
            logger.info("%s: fetched %d jobs", crawler_name, len(jobs))

            try:
                ingest_summary = ingest_jobs(jobs, config, conn)
            except Exception as exc:
                logger.error("ingest_jobs failed for %s: %s", crawler_name, exc)
                continue

            total_inserted += ingest_summary.get("inserted", 0)
            total_duplicates += ingest_summary.get("skipped_duplicate", 0)
            total_rejected += ingest_summary.get("rejected", 0)
            logger.info(
                "%s: inserted=%d duplicates=%d rejected=%d",
                crawler_name,
                ingest_summary.get("inserted", 0),
                ingest_summary.get("skipped_duplicate", 0),
                ingest_summary.get("rejected", 0),
            )

        # All ingestion complete. Dispatch runs exactly once, after every batch.
        try:
            dispatch_result = dispatch_new_jobs(config, conn)
            logger.info(
                "dispatch: eligible=%d notified=%d both_failed=%d",
                dispatch_result.get("eligible", 0),
                dispatch_result.get("notified", 0),
                dispatch_result.get("both_failed", 0),
            )
        except Exception as exc:
            logger.error("dispatch_new_jobs failed: %s", exc)
            dispatch_failed = True

    finally:
        conn.close()

    summary = {
        **crawler_counts,
        "inserted_jobs": total_inserted,
        "duplicate_jobs": total_duplicates,
        "rejected_jobs": total_rejected,
        "notifications_sent": dispatch_result.get("notified", 0),
        "notification_failures": dispatch_result.get("both_failed", 0),
        "dispatch_failed": dispatch_failed,
    }
    logger.info("run_pipeline complete: %s", summary)
    return summary
