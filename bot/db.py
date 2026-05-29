import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "raid.db")


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with row_factory and foreign keys enabled.

    WAL mode is not set here — it is set once in init_db() and persists in the
    database file, so it does not need to be repeated on every connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist and safely apply any new-column migrations."""
    conn = get_connection()

    # WAL mode is set once here — it is persistent, no need to repeat per connection
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS raid_sessions (
            id            TEXT PRIMARY KEY,
            template_key  TEXT NOT NULL,
            template_name TEXT NOT NULL,
            date_time     TEXT NOT NULL,
            created_by    TEXT NOT NULL,
            message_id    TEXT,
            channel_id    TEXT,
            created_at    TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'active',
            expires_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS raid_slots (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       TEXT NOT NULL REFERENCES raid_sessions(id) ON DELETE CASCADE,
            slot_index       INTEGER NOT NULL,
            role             TEXT NOT NULL,
            category         TEXT NOT NULL,
            claimed_by       TEXT,
            claimed_username TEXT
        );
    """)

    # Safe migration: add new columns without touching existing data
    for col, definition in [
        ("status",     "TEXT NOT NULL DEFAULT 'active'"),
        ("expires_at", "TEXT"),
        ("guild_id",   "INT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE raid_sessions ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Back-fill expires_at for old rows that have no value
    conn.execute("""
        UPDATE raid_sessions
        SET expires_at = datetime(created_at, '+24 hours')
        WHERE expires_at IS NULL
    """)

    conn.commit()
    conn.close()
