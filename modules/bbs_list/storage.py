import sqlite3
import time
from pathlib import Path

from rsmesh_bbs.sqlite_config import configure_sqlite_connection

_MODULE_DIR = Path(__file__).resolve().parent
DB_PATH = None

RECORD_TYPE = "module:bbs_list"
WIRE_SUFFIX = "SYNC"
MESH_LOCATION_MAX_LEN = 16

_CREATE_TABLE_SQL = """CREATE TABLE IF NOT EXISTS bbs_entries (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               node_hex TEXT NOT NULL UNIQUE,
               board_name TEXT NOT NULL,
               short_name TEXT NOT NULL,
               location TEXT,
               sync_interest TEXT NOT NULL DEFAULT 'N',
               is_local TEXT NOT NULL DEFAULT 'N',
               updated INTEGER NOT NULL
           )"""


def wire_type():
    from rsmesh_bbs.module_sync import build_module_wire_type

    return build_module_wire_type("bbs_list", WIRE_SUFFIX)


def configure(module_dir=None):
    global DB_PATH
    module_path = Path(module_dir) if module_dir is not None else _MODULE_DIR
    DB_PATH = str(module_path / "bbs_list.db")
    setup_db()


def _connect():
    if DB_PATH is None:
        configure()
    conn = sqlite3.connect(DB_PATH)
    configure_sqlite_connection(conn)
    return conn


def _table_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def _migrate_legacy_schema(cursor):
    columns = _table_columns(cursor, "bbs_entries")
    if not columns:
        return
    if "id" in columns:
        return
    cursor.execute(
        """CREATE TABLE bbs_entries_new (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               node_hex TEXT NOT NULL UNIQUE,
               board_name TEXT NOT NULL,
               short_name TEXT NOT NULL,
               location TEXT,
               sync_interest TEXT NOT NULL DEFAULT 'N',
               is_local TEXT NOT NULL DEFAULT 'N',
               updated INTEGER NOT NULL
           )"""
    )
    cursor.execute(
        """INSERT INTO bbs_entries_new
           (node_hex, board_name, short_name, location, sync_interest, is_local, updated)
           SELECT node_hex, board_name, short_name, location, sync_interest, is_local, updated
           FROM bbs_entries
           ORDER BY rowid"""
    )
    cursor.execute("DROP TABLE bbs_entries")
    cursor.execute("ALTER TABLE bbs_entries_new RENAME TO bbs_entries")


def setup_db():
    conn = _connect()
    c = conn.cursor()
    c.execute(_CREATE_TABLE_SQL)
    _migrate_legacy_schema(c)
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_bbs_entries_sync "
        "ON bbs_entries(sync_interest, board_name COLLATE NOCASE)"
    )
    conn.commit()
    conn.close()


def normalize_node_hex(value):
    text = (value or "").strip()
    if not text:
        return ""
    if not text.startswith("!"):
        text = "!" + text
    return text.lower()


def normalize_short_name(value):
    return (value or "").strip()[:4]


def normalize_sync_interest(value):
    return "Y" if (value or "").strip().upper() == "Y" else "N"


def _parse_entry_id(value):
    try:
        entry_id = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if entry_id <= 0:
        return None
    return entry_id


def _row_to_entry(row):
    if row is None:
        return None
    return {
        "id": row[0],
        "node_hex": row[1],
        "board_name": row[2],
        "short_name": row[3],
        "location": row[4] or "",
        "sync_interest": row[5],
        "is_local": row[6],
        "updated": row[7],
    }


def list_entries(sync_only=False):
    conn = _connect()
    c = conn.cursor()
    if sync_only:
        c.execute(
            "SELECT id, node_hex, board_name, short_name, location, sync_interest, is_local, updated "
            "FROM bbs_entries WHERE sync_interest = 'Y' "
            "ORDER BY id"
        )
    else:
        c.execute(
            "SELECT id, node_hex, board_name, short_name, location, sync_interest, is_local, updated "
            "FROM bbs_entries ORDER BY id"
        )
    rows = [_row_to_entry(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_entry_by_id(entry_id):
    entry_id = _parse_entry_id(entry_id)
    if entry_id is None:
        return None
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, node_hex, board_name, short_name, location, sync_interest, is_local, updated "
        "FROM bbs_entries WHERE id = ?",
        (entry_id,),
    )
    row = _row_to_entry(c.fetchone())
    conn.close()
    return row


def get_entry(node_hex):
    node_hex = normalize_node_hex(node_hex)
    if not node_hex:
        return None
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, node_hex, board_name, short_name, location, sync_interest, is_local, updated "
        "FROM bbs_entries WHERE node_hex = ?",
        (node_hex,),
    )
    row = _row_to_entry(c.fetchone())
    conn.close()
    return row


def upsert_entry(
    board_name,
    node_hex,
    short_name,
    location=None,
    sync_interest="N",
    is_local="N",
):
    node_hex = normalize_node_hex(node_hex)
    board_name = (board_name or "").strip()
    short_name = normalize_short_name(short_name)
    location = (location or "").strip()
    sync_interest = normalize_sync_interest(sync_interest)
    is_local = "Y" if (is_local or "N").strip().upper() == "Y" else "N"
    if not node_hex or not board_name or not short_name:
        return None

    conn = _connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO bbs_entries
           (node_hex, board_name, short_name, location, sync_interest, is_local, updated)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(node_hex) DO UPDATE SET
               board_name = excluded.board_name,
               short_name = excluded.short_name,
               location = excluded.location,
               sync_interest = excluded.sync_interest,
               is_local = excluded.is_local,
               updated = excluded.updated""",
        (
            node_hex,
            board_name,
            short_name,
            location,
            sync_interest,
            is_local,
            int(time.time()),
        ),
    )
    c.execute("SELECT id FROM bbs_entries WHERE node_hex = ?", (node_hex,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else None


def delete_entry_by_id(entry_id):
    entry_id = _parse_entry_id(entry_id)
    if entry_id is None:
        return False
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM bbs_entries WHERE id = ?", (entry_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def delete_entry(node_hex):
    node_hex = normalize_node_hex(node_hex)
    if not node_hex:
        return False
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM bbs_entries WHERE node_hex = ?", (node_hex,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def upsert_from_wire(fields):
    node_hex = normalize_node_hex(fields.get("uid"))
    if not node_hex:
        return None
    existing = get_entry(node_hex)
    if existing and existing.get("is_local") == "Y":
        return None
    return upsert_entry(
        board_name=(fields.get("bn") or "").strip(),
        node_hex=node_hex,
        short_name=normalize_short_name(fields.get("sn")),
        location=(fields.get("loc") or "").strip(),
        sync_interest=normalize_sync_interest(fields.get("si")),
        is_local="N",
    )


def entry_to_wire(entry):
    return {
        "uid": entry["node_hex"],
        "bn": entry["board_name"],
        "sn": entry["short_name"],
        "loc": entry.get("location") or "",
        "si": entry.get("sync_interest") or "N",
    }


def list_unsynced_items():
    return [
        (entry["node_hex"], f"{entry['id']} {entry['board_name']}")
        for entry in list_entries()
    ]


def _mesh_location_label(location):
    text = (location or "").strip() or "-"
    if len(text) <= MESH_LOCATION_MAX_LEN:
        return text
    if MESH_LOCATION_MAX_LEN <= 1:
        return text[:MESH_LOCATION_MAX_LEN]
    return text[: MESH_LOCATION_MAX_LEN - 1].rstrip() + "…"


def format_list_line(entry):
    """Admin list line: all fields, full location."""
    location = entry["location"] or "-"
    parts = [
        entry["short_name"],
        entry["board_name"],
        entry["node_hex"],
        location,
        f"sync={entry['sync_interest']}",
        f"local={entry['is_local']}",
    ]
    return "  ".join(parts)


def format_mesh_list_line(entry):
    """Mesh list line: list ID, short name, board name, node, truncated location, sync *."""
    parts = [
        str(entry["id"]),
        entry["short_name"],
        entry["board_name"],
        entry["node_hex"],
        _mesh_location_label(entry.get("location")),
    ]
    line = "  ".join(parts)
    if entry.get("sync_interest") == "Y":
        line += " *"
    return line


def format_mesh_detail(entry):
    sync_label = "Yes" if entry["sync_interest"] == "Y" else "No"
    local_label = "Yes" if entry["is_local"] == "Y" else "No"
    lines = [
        f"ID: {entry['id']}",
        f"Board: {entry['board_name']}",
        f"Node: {entry['node_hex']}",
        f"Short: {entry['short_name']}",
        f"Location: {entry['location'] or '-'}",
        f"Sync interest: {sync_label}",
        f"Local entry: {local_label}",
    ]
    return "\n".join(lines)


def format_admin_lines(sync_only=False):
    entries = list_entries(sync_only=sync_only)
    if not entries:
        return []
    return [format_list_line(entry) for entry in entries]
