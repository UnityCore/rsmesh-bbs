import logging
import sqlite3
import time
from pathlib import Path

import yaml

from rsmesh_bbs.time_format import format_timestamp
from rsmesh_bbs.utils import join_display_fields
from rsmesh_bbs.sqlite_config import configure_sqlite_connection

_MODULE_DIR = Path(__file__).resolve().parent
DB_PATH = None
SCHEDULE_MINUTES = 1
MAX_VISITS = 5


def configure(module_dir=None):
    global DB_PATH, SCHEDULE_MINUTES, MAX_VISITS
    module_path = Path(module_dir) if module_dir is not None else _MODULE_DIR
    config_path = module_path / "config.yml"
    if config_path.exists():
        with config_path.open(encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        try:
            SCHEDULE_MINUTES = max(1, int(config.get("schedule_minutes", 1)))
        except (TypeError, ValueError):
            SCHEDULE_MINUTES = 1
        try:
            MAX_VISITS = max(1, int(config.get("max_visits", 5)))
        except (TypeError, ValueError):
            MAX_VISITS = 5
    DB_PATH = str(module_path / "example_hello.db")
    setup_db()


def _connect():
    if DB_PATH is None:
        configure()
    conn = sqlite3.connect(DB_PATH)
    configure_sqlite_connection(conn)
    return conn


def setup_db():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS visits (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               sender_id INTEGER NOT NULL,
               short_name TEXT NOT NULL,
               visited_at INTEGER NOT NULL,
               greet_pending TEXT NOT NULL DEFAULT 'Y'
           )"""
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_visits_visited_at "
        "ON visits(visited_at DESC, id DESC)"
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_visits_greet_pending "
        "ON visits(greet_pending, visited_at)"
    )
    conn.commit()
    conn.close()


def record_visit(sender_id, short_name):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO visits (sender_id, short_name, visited_at, greet_pending)
           VALUES (?, ?, ?, 'Y')""",
        (int(sender_id), short_name, int(time.time())),
    )
    conn.commit()
    conn.close()


def get_pending_greetings():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, sender_id, short_name FROM visits "
        "WHERE greet_pending = 'Y' ORDER BY visited_at, id"
    )
    rows = c.fetchall()
    conn.close()
    return rows


def mark_greetings_sent(visit_ids):
    if not visit_ids:
        return
    conn = _connect()
    c = conn.cursor()
    placeholders = ",".join("?" for _ in visit_ids)
    c.execute(
        f"UPDATE visits SET greet_pending = 'N' WHERE id IN ({placeholders})",
        visit_ids,
    )
    conn.commit()
    conn.close()


def trim_visits():
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM visits")
    total = c.fetchone()[0]
    if total <= MAX_VISITS:
        conn.close()
        return 0
    c.execute(
        "SELECT id FROM visits ORDER BY visited_at DESC, id DESC LIMIT -1 OFFSET ?",
        (MAX_VISITS,),
    )
    stale_ids = [row[0] for row in c.fetchall()]
    if stale_ids:
        placeholders = ",".join("?" for _ in stale_ids)
        c.execute(f"DELETE FROM visits WHERE id IN ({placeholders})", stale_ids)
        conn.commit()
        logging.info("example_hello trimmed %s visit record(s)", len(stale_ids))
    conn.close()
    return len(stale_ids)


def list_visit_lines():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT short_name, visited_at, greet_pending FROM visits "
        "ORDER BY visited_at DESC, id DESC"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return []
    lines = []
    for short_name, visited_at, greet_pending in rows:
        status = "pending" if greet_pending == "Y" else "sent"
        lines.append(
            join_display_fields(
                short_name,
                format_timestamp(visited_at),
                f"greeting {status}",
            )
        )
    return lines
