import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory and foreign key enforcement."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
