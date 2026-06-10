"""Scheduler entry point for the Job Intelligence Platform.

Run via: python src/scheduler/main.py

Owns: config loading, one-time migration at startup, scheduling loop.
Does not own: pipeline logic (delegated to runner.run_pipeline),
              DB connections (owned by runner), crawling, notifications.
"""
from __future__ import annotations

import logging
import time

import schedule

from src.config_loader import get_config
from src.db.migrations import run_migrations
from src.scheduler.runner import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    config = get_config()
    interval = int(config.get("schedule_interval_minutes", 60))

    logger.info("Applying migrations to %s", config["database_path"])
    run_migrations(config["database_path"])
    logger.info("Migrations complete.")

    logger.info("Scheduler starting. Run interval: %d minutes.", interval)
    schedule.every(interval).minutes.do(lambda: run_pipeline(config))

    logger.info("Running pipeline immediately on startup.")
    run_pipeline(config)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
