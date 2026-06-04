import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CURRENT_VERSION = 1
_SCHEMA_SQL = Path(__file__).parent / "schema.sql"


def run_migrations(db_path: str) -> None:
    """Apply pending migrations to the database at db_path. Safe to call repeatedly."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        current = _get_version(conn)
        if current >= CURRENT_VERSION:
            logger.info("Schema already at version %d, nothing to apply.", current)
            return
        _apply_v1(conn)
        logger.info("Migrated database to version %d.", CURRENT_VERSION)
    finally:
        conn.close()


def _get_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    result = conn.execute("SELECT version FROM schema_version").fetchone()
    return result[0] if result else 0


def _apply_v1(conn: sqlite3.Connection) -> None:
    # executescript issues an implicit COMMIT before running DDL.
    conn.executescript(_SCHEMA_SQL.read_text())
    conn.execute("PRAGMA journal_mode=WAL")
    applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
        (CURRENT_VERSION, applied_at),
    )
    conn.commit()
