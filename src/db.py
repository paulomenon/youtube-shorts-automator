import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional


_DB_PATH: Optional[str] = None


def init_db(db_path: str) -> None:
    """Initialize the database and create tables if they don't exist."""
    global _DB_PATH
    _DB_PATH = db_path

    with _connect() as conn:
        conn.executescript(_SCHEMA)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT NOT NULL,
    filepath        TEXT NOT NULL UNIQUE,
    duration        REAL,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'completed', 'cancelled')),
    max_shorts      INTEGER NOT NULL DEFAULT 5,
    shorts_created  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shorts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    clip_index      INTEGER NOT NULL,
    start_time      REAL NOT NULL,
    end_time        REAL NOT NULL,
    output_path     TEXT,
    caption_path    TEXT,
    title           TEXT,
    description     TEXT,
    hashtags        TEXT,
    upload_status   TEXT NOT NULL DEFAULT 'pending'
                        CHECK (upload_status IN ('pending', 'scheduled', 'uploaded', 'failed')),
    scheduled_at    TEXT,
    youtube_video_id TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_shorts_job_id ON shorts(job_id);
CREATE INDEX IF NOT EXISTS idx_shorts_upload_status ON shorts(upload_status);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def create_job(filename: str, filepath: str, duration: Optional[float], max_shorts: int) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (filename, filepath, duration, max_shorts) VALUES (?, ?, ?, ?)",
            (filename, filepath, duration, max_shorts),
        )
        return cur.lastrowid


def get_job(job_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def get_job_by_filepath(filepath: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE filepath = ?", (filepath,)).fetchone()
        return dict(row) if row else None


def get_all_jobs() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_jobs_by_status(status: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC", (status,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_job_status(job_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.utcnow().isoformat(), job_id),
        )


def update_job_duration(job_id: int, duration: float) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET duration = ?, updated_at = ? WHERE id = ?",
            (duration, datetime.utcnow().isoformat(), job_id),
        )


def increment_shorts_created(job_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET shorts_created = shorts_created + 1, updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), job_id),
        )


# ---------------------------------------------------------------------------
# Shorts
# ---------------------------------------------------------------------------

def create_short(
    job_id: int,
    clip_index: int,
    start_time: float,
    end_time: float,
    output_path: Optional[str] = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO shorts (job_id, clip_index, start_time, end_time, output_path)
               VALUES (?, ?, ?, ?, ?)""",
            (job_id, clip_index, start_time, end_time, output_path),
        )
        return cur.lastrowid


def get_short(short_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM shorts WHERE id = ?", (short_id,)).fetchone()
        return dict(row) if row else None


def get_shorts_for_job(job_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM shorts WHERE job_id = ? ORDER BY clip_index ASC", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_shorts_by_upload_status(status: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM shorts WHERE upload_status = ? ORDER BY scheduled_at ASC", (status,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_next_pending_short() -> Optional[dict]:
    """Get the next short that is pending upload, ordered by scheduled time."""
    with _connect() as conn:
        row = conn.execute(
            """SELECT * FROM shorts
               WHERE upload_status = 'pending' AND output_path IS NOT NULL
               ORDER BY scheduled_at ASC NULLS LAST, id ASC
               LIMIT 1"""
        ).fetchone()
        return dict(row) if row else None


def update_short_paths(short_id: int, output_path: str, caption_path: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE shorts SET output_path = ?, caption_path = ? WHERE id = ?",
            (output_path, caption_path, short_id),
        )


def update_short_metadata(
    short_id: int, title: str, description: str, hashtags: str
) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE shorts SET title = ?, description = ?, hashtags = ? WHERE id = ?",
            (title, description, hashtags, short_id),
        )


def update_short_schedule(short_id: int, scheduled_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE shorts SET scheduled_at = ?, upload_status = 'scheduled' WHERE id = ?",
            (scheduled_at, short_id),
        )


def update_short_upload_status(
    short_id: int,
    status: str,
    youtube_video_id: Optional[str] = None,
) -> None:
    with _connect() as conn:
        if youtube_video_id:
            conn.execute(
                "UPDATE shorts SET upload_status = ?, youtube_video_id = ? WHERE id = ?",
                (status, youtube_video_id, short_id),
            )
        else:
            conn.execute(
                "UPDATE shorts SET upload_status = ? WHERE id = ?", (status, short_id)
            )


def increment_short_retry(short_id: int) -> int:
    """Increment retry count and return the new value."""
    with _connect() as conn:
        conn.execute(
            "UPDATE shorts SET retry_count = retry_count + 1 WHERE id = ?", (short_id,)
        )
        row = conn.execute(
            "SELECT retry_count FROM shorts WHERE id = ?", (short_id,)
        ).fetchone()
        return row["retry_count"]


def reset_short(short_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE shorts
               SET upload_status = 'pending', retry_count = 0, youtube_video_id = NULL
               WHERE id = ?""",
            (short_id,),
        )


def reset_job(job_id: int) -> None:
    """Reset a job and all its shorts for reprocessing."""
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'pending', shorts_created = 0, updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), job_id),
        )
        conn.execute(
            """UPDATE shorts
               SET upload_status = 'pending', retry_count = 0,
                   youtube_video_id = NULL, output_path = NULL, caption_path = NULL
               WHERE job_id = ?""",
            (job_id,),
        )


def cancel_job_by_filepath(filepath: str) -> None:
    """Mark a job as cancelled when its source file is removed."""
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'cancelled', updated_at = ? WHERE filepath = ? AND status != 'completed'",
            (datetime.utcnow().isoformat(), filepath),
        )


def get_resumable_jobs() -> list[dict]:
    """Get jobs that were processing when the app last stopped."""
    return get_jobs_by_status("processing")
