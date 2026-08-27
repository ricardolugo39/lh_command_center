from pathlib import Path
import sqlite3
import os

from app.storage import data_path


def database_path() -> Path:
    configured = os.getenv("DATABASE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return data_path("database", "commercial.db")


DB_PATH = database_path()
SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = SQLITE_TIMEOUT_SECONDS * 1000


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    journal_mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if str(journal_mode).casefold() != "wal":
        conn.close()
        raise RuntimeError(
            "No fue posible habilitar el modo WAL de SQLite."
        )
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")

    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        conn.close()
        raise RuntimeError(
            "No fue posible habilitar PRAGMA foreign_keys."
        )

    return conn
