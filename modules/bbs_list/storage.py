import sqlite3
import time
from pathlib import Path

from rsmesh_bbs.sqlite_config import configure_sqlite_connection
from rsmesh_bbs.utils import join_display_fields

_MODULE_DIR = Path(__file__).resolve().parent
DB_PATH = None

RECORD_TYPE = "module:bbs_list"
WIRE_SUFFIX = "SYNC"


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


def setup_db():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS bbs_entries (
               node_hex TEXT PRIMARY KEY,
               board_name TEXT NOT NULL,
               short_name TEXT NOT NULL,
               location TEXT,
               sync_interest TEXT NOT NULL DEFAULT 'N',
               is_local TEXT NOT NULL DEFAULT 'N',
               updated INTEGER NOT NULL
           )"""
    )
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


def _row_to_entry(row):
    if row is None:
        return None
    return {
        "node_hex": row[0],
        "board_name": row[1],
        "short_name": row[2],
        "location": row[3] or "",
        "sync_interest": row[4],
        "is_local": row[5],
        "updated": row[6],
    }


def list_entries(sync_only=False):
    conn = _connect()
    c = conn.cursor()
    if sync_only:
        c.execute(
            "SELECT node_hex, board_name, short_name, location, sync_interest, is_local, updated "
            "FROM bbs_entries WHERE sync_interest = 'Y' "
            "ORDER BY board_name COLLATE NOCASE, node_hex"
        )
    else:
        c.execute(
            "SELECT node_hex, board_name, short_name, location, sync_interest, is_local, updated "
            "FROM bbs_entries ORDER BY board_name COLLATE NOCASE, node_hex"
        )
    rows = [_row_to_entry(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_entry(node_hex):
    node_hex = normalize_node_hex(node_hex)
    if not node_hex:
        return None
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT node_hex, board_name, short_name, location, sync_interest, is_local, updated "
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
        return False

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
    conn.commit()
    conn.close()
    return True


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
        return False
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
    return [(entry["node_hex"], entry["board_name"]) for entry in list_entries()]


def format_mesh_list_line(entry):
    marker = "*" if entry["sync_interest"] == "Y" else " "
    location = entry["location"] or "-"
    board_name = entry["board_name"]
    if len(board_name) > 18:
        board_name = board_name[:17] + "…"
    if len(location) > 12:
        location = location[:11] + "…"
    return f"{entry['short_name']} {board_name} {location}{marker}"


def format_mesh_detail(entry):
    sync_label = "Yes" if entry["sync_interest"] == "Y" else "No"
    local_label = "Yes" if entry["is_local"] == "Y" else "No"
    lines = [
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
    lines = []
    for entry in entries:
        fields = [
            entry["short_name"],
            entry["board_name"],
            entry["node_hex"],
        ]
        if entry["location"]:
            fields.append(entry["location"])
        if entry["sync_interest"] == "Y":
            fields.append("sync=Y")
        if entry["is_local"] == "Y":
            fields.append("local")
        lines.append(join_display_fields(*fields))
    return lines
