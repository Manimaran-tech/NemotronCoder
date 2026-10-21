"""
SQLite database for tracking automation progress.
Allows resuming from where we left off across sessions.
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path

# Check for isolated DB path
import os
def get_db_path() -> Path:
    env_db_path = os.environ.get("AGENT_DB_PATH")
    if env_db_path:
        db_path = Path(env_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path
    return Path(__file__).parent.parent / "progress.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating tables if needed."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level INTEGER NOT NULL,
            language TEXT NOT NULL DEFAULT 'c',
            module_index INTEGER NOT NULL,
            module_name TEXT NOT NULL DEFAULT '',
            total_chapters INTEGER DEFAULT 0,
            solved_chapters INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            discovered_at TEXT,
            completed_at TEXT,
            UNIQUE(level, language, module_index)
        );

        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            chapter_index INTEGER NOT NULL,
            chapter_name TEXT NOT NULL DEFAULT '',
            total_problems INTEGER DEFAULT 0,
            solved_problems INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            FOREIGN KEY (module_id) REFERENCES modules(id),
            UNIQUE(module_id, chapter_index)
        );

        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL,
            problem_id TEXT NOT NULL DEFAULT '',
            problem_type TEXT DEFAULT 'full',
            language TEXT DEFAULT 'c',
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            solved_at TEXT,
            error_log TEXT DEFAULT '',
            FOREIGN KEY (chapter_id) REFERENCES chapters(id)
        );

        CREATE TABLE IF NOT EXISTS session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            problems_attempted INTEGER DEFAULT 0,
            problems_solved INTEGER DEFAULT 0,
            target_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS captcha_pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_b64 TEXT NOT NULL,
            answer TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()


# ─────────────────────────── MODULE TRACKING ───────────────────────────

def upsert_module(level: int, language: str, module_index: int,
                  module_name: str = "", total_chapters: int = 0) -> int:
    """Insert or update a module. Returns module ID."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO modules (level, language, module_index, module_name, total_chapters, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(level, language, module_index) DO UPDATE SET
                module_name = COALESCE(NULLIF(excluded.module_name, ''), module_name),
                total_chapters = CASE WHEN excluded.total_chapters > 0 THEN excluded.total_chapters ELSE total_chapters END
        """, (level, language, module_index, module_name, total_chapters, datetime.now().isoformat()))
        conn.commit()

        row = conn.execute(
            "SELECT id FROM modules WHERE level=? AND language=? AND module_index=?",
            (level, language, module_index)
        ).fetchone()
        return row["id"]
    finally:
        conn.close()


def mark_module_completed(module_id: int):
    """Mark a module as completed."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE modules SET status='completed', completed_at=? WHERE id=?",
            (datetime.now().isoformat(), module_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_next_unsolved_module(level: int = None, language: str = None) -> dict | None:
    """Get the next unsolved module. Returns dict or None."""
    conn = get_connection()
    try:
        query = "SELECT * FROM modules WHERE status != 'completed'"
        params = []
        if level is not None:
            query += " AND level = ?"
            params.append(level)
        if language is not None:
            query += " AND language = ?"
            params.append(language)
        query += " ORDER BY level, module_index LIMIT 1"
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_modules(level: int = None) -> list[dict]:
    """Get all modules, optionally filtered by level."""
    conn = get_connection()
    try:
        query = "SELECT * FROM modules"
        params = []
        if level is not None:
            query += " WHERE level = ?"
            params.append(level)
        query += " ORDER BY level, module_index"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─────────────────────────── CHAPTER TRACKING ───────────────────────────

def upsert_chapter(module_id: int, chapter_index: int,
                   chapter_name: str = "", total_problems: int = 0) -> int:
    """Insert or update a chapter. Returns chapter ID."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO chapters (module_id, chapter_index, chapter_name, total_problems, started_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(module_id, chapter_index) DO UPDATE SET
                chapter_name = COALESCE(NULLIF(excluded.chapter_name, ''), chapter_name),
                total_problems = CASE WHEN excluded.total_problems > 0 THEN excluded.total_problems ELSE total_problems END
        """, (module_id, chapter_index, chapter_name, total_problems, datetime.now().isoformat()))
        conn.commit()

        row = conn.execute(
            "SELECT id FROM chapters WHERE module_id=? AND chapter_index=?",
            (module_id, chapter_index)
        ).fetchone()
        return row["id"]
    finally:
        conn.close()


def mark_chapter_completed(chapter_id: int):
    """Mark a chapter as completed."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE chapters SET status='completed', completed_at=? WHERE id=?",
            (datetime.now().isoformat(), chapter_id)
        )
        # Update parent module solved count
        conn.execute("""
            UPDATE modules SET solved_chapters = (
                SELECT COUNT(*) FROM chapters WHERE module_id = modules.id AND status = 'completed'
            ) WHERE id = (SELECT module_id FROM chapters WHERE id = ?)
        """, (chapter_id,))
        conn.commit()
    finally:
        conn.close()


def get_next_unsolved_chapter(module_id: int) -> dict | None:
    """Get the next unsolved chapter in a module."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM chapters WHERE module_id=? AND status != 'completed' ORDER BY chapter_index LIMIT 1",
            (module_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ─────────────────────────── PROBLEM TRACKING ───────────────────────────

def record_problem_attempt(chapter_id: int, problem_id: str, language: str,
                           problem_type: str = "full"):
    """Record a problem attempt."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO problems (chapter_id, problem_id, language, problem_type, status, attempts)
            VALUES (?, ?, ?, ?, 'attempting', 1)
        """, (chapter_id, problem_id, language, problem_type))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def mark_problem_solved(problem_db_id: int):
    """Mark a problem as solved."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE problems SET status='solved', solved_at=? WHERE id=?",
            (datetime.now().isoformat(), problem_db_id)
        )
        # Update chapter solved count
        conn.execute("""
            UPDATE chapters SET solved_problems = (
                SELECT COUNT(*) FROM problems WHERE chapter_id = chapters.id AND status = 'solved'
            ) WHERE id = (SELECT chapter_id FROM problems WHERE id = ?)
        """, (problem_db_id,))
        conn.commit()
    finally:
        conn.close()


def mark_problem_failed(problem_db_id: int, error: str = ""):
    """Mark a problem as failed."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE problems SET status='failed', error_log=? WHERE id=?",
            (error[:1000], problem_db_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_failed_problems_count(chapter_id: int) -> int:
    """Get the number of failed problems in a chapter."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) FROM problems WHERE chapter_id=? AND status='failed'", (chapter_id,)).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()



# ─────────────────────────── SESSION TRACKING ───────────────────────────

def start_session(target_count: int) -> int:
    """Start a new session. Returns session ID."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO session_log (started_at, target_count) VALUES (?, ?)",
            (datetime.now().isoformat(), target_count)
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def update_session(session_id: int, attempted: int, solved: int):
    """Update session stats."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE session_log SET problems_attempted=?, problems_solved=?, ended_at=? WHERE id=?",
            (attempted, solved, datetime.now().isoformat(), session_id)
        )
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────── PROGRESS SUMMARY ───────────────────────────

def get_total_solved() -> int:
    """Get total number of solved problems across all sessions."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM problems WHERE status='solved'").fetchone()
        return row["cnt"]
    finally:
        conn.close()


def print_progress():
    """Print a formatted progress summary."""
    conn = get_connection()
    try:
        total_solved = conn.execute("SELECT COUNT(*) FROM problems WHERE status='solved'").fetchone()[0]
        total_failed = conn.execute("SELECT COUNT(*) FROM problems WHERE status='failed'").fetchone()[0]
        total_modules = conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
        completed_modules = conn.execute("SELECT COUNT(*) FROM modules WHERE status='completed'").fetchone()[0]

        print(f"\n{'=' * 50}")
        print(f"  PROGRESS SUMMARY")
        print(f"{'=' * 50}")
        print(f"  Problems Solved:  {total_solved}")
        print(f"  Problems Failed:  {total_failed}")
        print(f"  Modules Total:    {total_modules}")
        print(f"  Modules Done:     {completed_modules}")
        print(f"{'=' * 50}")

        # Per-module breakdown
        modules = conn.execute(
            "SELECT * FROM modules ORDER BY level, module_index"
        ).fetchall()
        if modules:
            print(f"\n  Module Breakdown:")
            for m in modules:
                status_icon = "[DONE]" if m["status"] == "completed" else "[....]"
                print(f"    {status_icon} L{m['level']} {m['module_name'][:40]:40s} "
                      f"({m['solved_chapters']}/{m['total_chapters']} chapters)")
        print()
    finally:
        conn.close()


# ─────────────────────────── CAPTCHA PENDING HELPERS ───────────────────────────

def add_captcha_request(image_b64: str) -> int:
    """Insert a new captcha request, clearing any existing ones first."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM captcha_pending")
        conn.execute(
            "INSERT INTO captcha_pending (image_b64, status, created_at) VALUES (?, 'pending', ?)",
            (image_b64, datetime.now().isoformat())
        )
        conn.commit()
        row = conn.execute("SELECT last_insert_rowid()").fetchone()
        return row[0]
    finally:
        conn.close()


def get_pending_captcha() -> dict | None:
    """Get the current pending captcha."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM captcha_pending WHERE status='pending' LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def solve_pending_captcha(captcha_id: int, answer: str):
    """Solve the pending captcha."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE captcha_pending SET answer=?, status='solved' WHERE id=?",
            (answer, captcha_id)
        )
        conn.commit()
    finally:
        conn.close()


def check_captcha_solved() -> str | None:
    """Check if the current captcha has been solved. Returns the answer, or None if still pending."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT answer FROM captcha_pending WHERE status='solved' LIMIT 1").fetchone()
        return row["answer"] if row else None
    finally:
        conn.close()


def clear_captcha():
    """Clear all captchas from database."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM captcha_pending")
        conn.commit()
    finally:
        conn.close()

