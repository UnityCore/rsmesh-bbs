import csv
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta


from .version import BBS_DB_FILE
from .config_init import DEFAULT_CONFIG_FILE, export_sys_config_to_yaml, flatten_yaml_config, load_config
from .sqlite_config import configure_sqlite_connection
from .tc2_migration import migrate_tc2_database
from .utils import (
    send_bulletin_to_sync_peers,
    send_delete_bulletin_to_sync_peers,
    send_delete_channel_to_sync_peers,
    send_delete_mail_to_bbs_nodes,
    send_mail_to_bbs_nodes, send_message, send_channel_to_bbs_nodes,
    get_sync_peers_from_interface,
    sync_peer_nodes,
    sync_peer_bbs_node,
    filter_peers_for_record_type,
)


thread_local = threading.local()

SYNC_PROTOCOLS = ('tc2', 'rsv1')

SYNCED_TABLES = ('bulletins', 'mail', 'channels')

RECORD_SYNC_KEY_COLUMNS = {
    'bulletins': 'unique_id',
    'mail': 'unique_id',
    'channels': 'unique_id',
}

PEER_SYNC_FLAG_COLUMNS = {
    'bulletins': 'sync_bulletins',
    'mail': 'sync_mail',
    'channels': 'sync_channels',
}

PEER_ROW_SELECT = (
    "id, bbs_node, bbs_name, sync_protocol, last_heard, "
    "sync_bulletins, sync_mail, sync_channels, sync_mesh_nodes, ingest_bulletins, ingest_channels, "
    "rs_version_alert, rs_wire_version_seen, enabled"
)

PEER_ENABLED_INDEX = 13


def _peer_id_for_bbs_node(bbs_node):
    bbs_node = (bbs_node or "").strip()
    if not bbs_node:
        return None
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM sync_peers WHERE bbs_node = ?", (bbs_node,))
    row = c.fetchone()
    return row[0] if row else None


def _resolve_peer_id(peer):
    peer_id = peer[0]
    if peer_id is not None:
        return peer_id

    from .utils import sync_peer_bbs_node
    bbs_node = sync_peer_bbs_node(peer)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM sync_peers WHERE bbs_node = ?", (bbs_node,))
    row = c.fetchone()
    return row[0] if row else None


def _get_synced_peer_ids(record_type, record_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT peer_id FROM record_sync_peers "
        "WHERE record_type = ? AND record_key = ? AND synced = 'Y'",
        (record_type, record_key),
    )
    return {row[0] for row in c.fetchall()}


def _count_synced_peers_for_record(record_type, record_key):
    flag_column = PEER_SYNC_FLAG_COLUMNS.get(record_type)
    if not flag_column:
        return len(_get_synced_peer_ids(record_type, record_key))
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        f"SELECT COUNT(*) FROM record_sync_peers rsp "
        f"JOIN sync_peers sp ON sp.id = rsp.peer_id "
        f"WHERE rsp.record_type = ? AND rsp.record_key = ? AND rsp.synced = 'Y' "
        f"AND sp.enabled = 'Y' AND sp.{flag_column} = 'Y'",
        (record_type, record_key),
    )
    return c.fetchone()[0]


def _normalize_sync_flag(value, default='Y'):
    normalized = (value or default).strip().upper()
    return 'Y' if normalized == 'Y' else 'N'


def _get_pending_peers(record_type, record_key, all_peers):
    eligible_peers = filter_peers_for_record_type(all_peers, record_type)
    synced_peer_ids = _get_synced_peer_ids(record_type, record_key)
    pending = []
    for peer in eligible_peers:
        peer_id = _resolve_peer_id(peer)
        if peer_id is None or peer_id not in synced_peer_ids:
            pending.append(peer)
    return pending


def _mark_peers_synced(record_type, record_key, peer_ids):
    if not peer_ids:
        return
    conn = get_db_connection()
    c = conn.cursor()
    for peer_id in peer_ids:
        c.execute(
            "INSERT INTO record_sync_peers (record_type, record_key, peer_id, synced) "
            "VALUES (?, ?, ?, 'Y') "
            "ON CONFLICT(record_type, record_key, peer_id) DO UPDATE SET synced = 'Y'",
            (record_type, record_key, peer_id),
        )
    conn.commit()


def _mark_inbound_sync_complete(record_type, record_key):
    flag_column = PEER_SYNC_FLAG_COLUMNS.get(record_type)
    if not flag_column:
        return
    conn = get_db_connection()
    c = conn.cursor()
    for (peer_id,) in c.execute(
        f"SELECT id FROM sync_peers WHERE enabled = 'Y' AND {flag_column} = 'Y'"
    ):
        c.execute(
            "INSERT INTO record_sync_peers (record_type, record_key, peer_id, synced) "
            "VALUES (?, ?, ?, 'Y') "
            "ON CONFLICT(record_type, record_key, peer_id) DO UPDATE SET synced = 'Y'",
            (record_type, record_key, peer_id),
        )
    conn.commit()


def _reset_record_peer_sync(record_type, record_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM record_sync_peers WHERE record_type = ? AND record_key = ?",
        (record_type, record_key),
    )
    conn.commit()


def reset_outbound_sync(record_type, record_key, id_column, id_value):
    if record_type not in SYNCED_TABLES:
        return
    _reset_record_peer_sync(record_type, record_key)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {record_type} SET synced = 'N' WHERE {id_column} = ?", (id_value,))
    conn.commit()


def _count_configured_sync_peers(record_type):
    flag_column = PEER_SYNC_FLAG_COLUMNS.get(record_type)
    conn = get_db_connection()
    c = conn.cursor()
    if not flag_column:
        c.execute("SELECT COUNT(*) FROM sync_peers WHERE enabled = 'Y'")
    else:
        c.execute(
            f"SELECT COUNT(*) FROM sync_peers WHERE enabled = 'Y' AND {flag_column} = 'Y'"
        )
    return c.fetchone()[0]


def _update_aggregate_synced(record_type, id_column, id_value, record_key):
    if record_type not in SYNCED_TABLES:
        return
    conn = get_db_connection()
    c = conn.cursor()
    if record_type == 'channels':
        c.execute("SELECT publish FROM channels WHERE unique_id = ?", (record_key,))
        row = c.fetchone()
        if row and row[0] != 'Y':
            c.execute(f"UPDATE channels SET synced = 'Y' WHERE {id_column} = ?", (id_value,))
            conn.commit()
            return
    peer_count = _count_configured_sync_peers(record_type)
    if peer_count == 0:
        synced = 'Y'
    else:
        synced_count = _count_synced_peers_for_record(record_type, record_key)
        synced = 'Y' if synced_count >= peer_count else 'N'
    c.execute(f"UPDATE {record_type} SET synced = ? WHERE {id_column} = ?", (synced, id_value))
    conn.commit()


def _refresh_all_aggregate_synced():
    conn = get_db_connection()
    c = conn.cursor()
    for table in SYNCED_TABLES:
        key_column = RECORD_SYNC_KEY_COLUMNS[table]
        rows = c.execute(f"SELECT {key_column}, {key_column} FROM {table}").fetchall()
        for record_key, id_value in rows:
            if record_key:
                _update_aggregate_synced(table, key_column, id_value, record_key)


def get_sync_status_label(record_type, record_key):
    peer_count = _count_configured_sync_peers(record_type)
    if peer_count == 0:
        return 'Y'
    synced_count = _count_synced_peers_for_record(record_type, record_key)
    if synced_count == 0:
        return 'N'
    if synced_count >= peer_count:
        return 'Y'
    return f'{synced_count}/{peer_count}'


def _get_pending_peer_labels(record_type, record_key, all_peers):
    synced_peer_ids = _get_synced_peer_ids(record_type, record_key)
    labels = []
    for peer in filter_peers_for_record_type(all_peers, record_type):
        peer_id = _resolve_peer_id(peer)
        if peer_id is None or peer_id not in synced_peer_ids:
            name = peer[2] if len(peer) > 2 and peer[2] else peer[1]
            labels.append(name or peer[1])
    return labels


def _mark_record_synced(table, id_column, id_value):
    if table not in SYNCED_TABLES:
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET synced = 'Y' WHERE {id_column} = ?", (id_value,))
    conn.commit()


def _sync_record_to_peers(record_type, record_key, id_column, id_value, peers, send_fn):
    pending = _get_pending_peers(record_type, record_key, peers)
    if not pending:
        _update_aggregate_synced(record_type, id_column, id_value, record_key)
        return True

    synced_peer_ids = send_fn(pending)
    if synced_peer_ids:
        resolved_ids = []
        for peer in synced_peer_ids:
            if isinstance(peer, int):
                resolved_ids.append(peer)
            else:
                peer_id = _resolve_peer_id(peer)
                if peer_id is not None:
                    resolved_ids.append(peer_id)
        _mark_peers_synced(record_type, record_key, resolved_ids)

    _update_aggregate_synced(record_type, id_column, id_value, record_key)
    remaining = _get_pending_peers(record_type, record_key, peers)
    return not remaining


def _complete_local_sync(table, id_column, id_value, record_key, sync_peers, interface, send_fn):
    if interface is None:
        return
    if table == 'channels':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT publish FROM channels WHERE unique_id = ?", (record_key,))
        row = c.fetchone()
        if row and row[0] != 'Y':
            _mark_record_synced(table, id_column, id_value)
            return
    peers = get_sync_peers_from_interface(interface, sync_peers)
    if not peers:
        _mark_record_synced(table, id_column, id_value)
        return
    if _sync_record_to_peers(table, record_key, id_column, id_value, peers, send_fn):
        logging.info(f"Synced {table} {record_key} to all peers.")
    else:
        pending_labels = _get_pending_peer_labels(table, record_key, peers)
        logging.warning(
            f"Sync not complete for {table} {record_key}; pending peers: {', '.join(pending_labels)}."
        )


def _record_needs_peer_sync_clause(record_type, table_alias, key_column):
    flag_column = PEER_SYNC_FLAG_COLUMNS[record_type]
    return f"""(
        {table_alias}.synced = 'N'
        OR EXISTS (
            SELECT 1 FROM sync_peers sp
            LEFT JOIN record_sync_peers rsp
              ON rsp.record_type = ?
             AND rsp.record_key = {table_alias}.{key_column}
             AND rsp.peer_id = sp.id
             AND rsp.synced = 'Y'
            WHERE sp.enabled = 'Y'
              AND sp.{flag_column} = 'Y'
              AND rsp.peer_id IS NULL
        )
    )"""


def sync_pending_records(sync_peers, interface):
    if interface is None:
        return

    peers = get_sync_peers_from_interface(interface, sync_peers)
    if not peers:
        return

    sync_pending_deletes(peers, interface)

    conn = get_db_connection()
    c = conn.cursor()
    bulletin_clause = _record_needs_peer_sync_clause('bulletins', 'b', 'unique_id')

    c.execute(
        f"SELECT board, sender_short_name, subject, content, unique_id FROM bulletins b "
        f"WHERE deleted = 'N' AND {bulletin_clause} ORDER BY b.id",
        ('bulletins',),
    )
    for board, sender_short_name, subject, content, unique_id in c.fetchall():
        def _send_bulletin(pending_peers):
            return send_bulletin_to_sync_peers(
                board, sender_short_name, subject, content, unique_id, pending_peers, interface
            )

        if _sync_record_to_peers('bulletins', unique_id, 'unique_id', unique_id, peers, _send_bulletin):
            logging.info(f"Synced bulletin {unique_id} to all peers.")
        else:
            logging.warning(f"Bulletin {unique_id} sync incomplete; will retry pending peers.")

    mail_clause = _record_needs_peer_sync_clause('mail', 'm', 'unique_id')
    c.execute(
        f"SELECT sender, sender_short_name, recipient, recipient_short_name, subject, content, unique_id "
        f"FROM mail m WHERE {mail_clause} ORDER BY m.id",
        ('mail',),
    )
    for sender_id, sender_short_name, recipient_id, recipient_short_name, subject, content, unique_id in c.fetchall():
        def _send_mail(pending_peers):
            return send_mail_to_bbs_nodes(
                sender_id, sender_short_name, recipient_id, recipient_short_name,
                subject, content, unique_id, pending_peers, interface,
            )

        if _sync_record_to_peers('mail', unique_id, 'unique_id', unique_id, peers, _send_mail):
            logging.info(f"Synced mail {unique_id} to all peers.")
        else:
            logging.warning(f"Mail {unique_id} sync incomplete; will retry pending peers.")

    channel_clause = _record_needs_peer_sync_clause('channels', 'c', 'unique_id')
    c.execute(
        f"SELECT id, name, psk, unique_id FROM channels c "
        f"WHERE publish = 'Y' AND deleted = 'N' AND {channel_clause} ORDER BY c.id",
        ('channels',),
    )
    for channel_id, name, psk, unique_id in c.fetchall():
        def _send_channel(pending_peers):
            return send_channel_to_bbs_nodes(
                name, psk, pending_peers, interface, unique_id=unique_id
            )

        if _sync_record_to_peers('channels', unique_id, 'unique_id', unique_id, peers, _send_channel):
            logging.info(f"Synced channel {name} to all peers.")
        else:
            logging.warning(f"Channel {name} sync incomplete; will retry pending peers.")

    sync_mesh_nodes_to_peers(peers, interface)

    from .node_resolution import scan_mesh_nodes_store
    scan_mesh_nodes_store(interface)


def get_unsynced_records():
    conn = get_db_connection()
    c = conn.cursor()
    peers = get_sync_peers()
    bulletin_clause = _record_needs_peer_sync_clause('bulletins', 'b', 'unique_id')
    mail_clause = _record_needs_peer_sync_clause('mail', 'm', 'unique_id')
    channel_clause = _record_needs_peer_sync_clause('channels', 'c', 'unique_id')

    c.execute(
        f"SELECT id, board, sender_short_name, subject, deleted, unique_id FROM bulletins b "
        f"WHERE deleted = 'N' AND {bulletin_clause} ORDER BY b.id",
        ('bulletins',),
    )
    bulletins = []
    for row in c.fetchall():
        pending = _get_pending_peer_labels('bulletins', row[5], peers)
        bulletins.append((*row, pending))

    c.execute(
        f"SELECT id, sender_short_name, recipient, subject, unique_id FROM mail m "
        f"WHERE {mail_clause} ORDER BY m.id",
        ('mail',),
    )
    mail_rows = []
    for row in c.fetchall():
        pending = _get_pending_peer_labels('mail', row[4], peers)
        mail_rows.append((*row, pending))

    c.execute(
        f"SELECT id, name, publish, unique_id FROM channels c "
        f"WHERE publish = 'Y' AND deleted = 'N' AND {channel_clause} ORDER BY c.id",
        ('channels',),
    )
    channels = []
    for row in c.fetchall():
        pending = _get_pending_peer_labels('channels', row[3], peers)
        channels.append((*row, pending))

    return bulletins, mail_rows, channels


def get_system_status():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM bulletins WHERE deleted = 'N'")
    total_bulletins = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM bulletins WHERE delete_reconcile = 'Y'")
    reconcile_bulletins = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM channels WHERE publish = 'Y' AND deleted = 'N'")
    channels_published = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM channels WHERE publish = 'N' AND deleted = 'N'")
    channels_unpublished = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM channels WHERE delete_reconcile = 'Y'")
    reconcile_channels = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM mail")
    total_mail = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM mail WHERE read = 'N'")
    unread_mail = c.fetchone()[0]

    return {
        'total_bulletins': total_bulletins,
        'reconcile_bulletins': reconcile_bulletins,
        'reconcile_channels': reconcile_channels,
        'channels_published': channels_published,
        'channels_unpublished': channels_unpublished,
        'total_mail': total_mail,
        'unread_mail': unread_mail,
        'sync_peers': get_sync_peers(),
        'rs_version_alert_count': count_rs_version_alerts(),
    }


def get_db_connection():
    if not hasattr(thread_local, 'connection'):
        thread_local.connection = sqlite3.connect(BBS_DB_FILE)
        configure_sqlite_connection(thread_local.connection)
    return thread_local.connection

def initialize_database(quiet=False):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bulletins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board TEXT NOT NULL,
                    sender_short_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content TEXT NOT NULL,
                    deleted TEXT NOT NULL DEFAULT 'N',
                    unique_id TEXT NOT NULL,
                    delete_reconcile TEXT NOT NULL DEFAULT 'N',
                    synced TEXT NOT NULL DEFAULT 'N',
                    pinned TEXT NOT NULL DEFAULT 'N'
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS mail (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    sender_short_name TEXT NOT NULL,
                    recipient TEXT,
                    recipient_short_name TEXT,
                    date TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content TEXT NOT NULL,
                    unique_id TEXT NOT NULL,
                    synced TEXT NOT NULL DEFAULT 'N',
                    read TEXT NOT NULL DEFAULT 'N'
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    psk TEXT NOT NULL,
                    publish TEXT NOT NULL DEFAULT 'Y',
                    synced TEXT NOT NULL DEFAULT 'N',
                    unique_id TEXT,
                    deleted TEXT NOT NULL DEFAULT 'N',
                    delete_reconcile TEXT NOT NULL DEFAULT 'N'
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sysadmin_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_name TEXT NOT NULL,
                    node_hex_username TEXT NOT NULL
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS node_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    long_name TEXT NOT NULL,
                    short_name TEXT NOT NULL,
                    node_hex_username TEXT NOT NULL,
                    mesh_admin TEXT NOT NULL DEFAULT 'N',
                    bbs_admin TEXT NOT NULL DEFAULT 'N',
                    bbs_mail_forward_to TEXT,
                    has_gps TEXT NOT NULL DEFAULT 'N',
                    public_key TEXT NOT NULL,
                    private_key TEXT,
                    ble_pin TEXT NOT NULL DEFAULT '123456',
                    hardware TEXT,
                    comment TEXT,
                    created TEXT NOT NULL,
                    updated TEXT NOT NULL
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sync_peers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bbs_node TEXT NOT NULL UNIQUE,
                    bbs_name TEXT,
                    sync_protocol TEXT NOT NULL DEFAULT 'tc2',
                    last_heard INTEGER,
                    sync_bulletins TEXT NOT NULL DEFAULT 'Y',
                    sync_mail TEXT NOT NULL DEFAULT 'Y',
                    sync_channels TEXT NOT NULL DEFAULT 'Y',
                    sync_mesh_nodes TEXT NOT NULL DEFAULT 'N',
                    ingest_bulletins TEXT NOT NULL DEFAULT 'Y',
                    ingest_channels TEXT NOT NULL DEFAULT 'Y',
                    rs_version_alert TEXT NOT NULL DEFAULT 'N',
                    rs_wire_version_seen INTEGER,
                    enabled TEXT NOT NULL DEFAULT 'Y'
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sys_config (
                    cfg_section TEXT NOT NULL,
                    cfg_key TEXT NOT NULL,
                    cfg_value TEXT,
                    PRIMARY KEY (cfg_section, cfg_key)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS modules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_name TEXT NOT NULL,
                    module_dir TEXT NOT NULL UNIQUE,
                    menu_option TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    enabled TEXT NOT NULL DEFAULT 'Y',
                    schedule_enabled TEXT NOT NULL DEFAULT 'N'
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS record_sync_peers (
                    record_type TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    peer_id INTEGER NOT NULL,
                    synced TEXT NOT NULL DEFAULT 'N',
                    PRIMARY KEY (record_type, record_key, peer_id),
                    FOREIGN KEY (peer_id) REFERENCES sync_peers(id) ON DELETE CASCADE
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesh_nodes (
                    node_id TEXT PRIMARY KEY,
                    short_name TEXT,
                    long_name TEXT,
                    last_heard INTEGER,
                    last_updated INTEGER NOT NULL
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_sync_deletes (
                    record_type TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    created TEXT NOT NULL,
                    PRIMARY KEY (record_type, record_key)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_urgent_alerts (
                    unique_id TEXT NOT NULL PRIMARY KEY,
                    sender_short_name TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    created TEXT NOT NULL
                )''')
    migrate_tc2_database(c)
    _ensure_default_modules(c)
    _ensure_database_indexes(c)
    conn.commit()
    if not quiet:
        print("Database schema initialized.")


def current_catalog_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M')


def _ensure_channels_indexes(c):
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_unique_id ON channels(unique_id)")
    duplicate_psks = c.execute(
        "SELECT psk FROM channels GROUP BY psk HAVING COUNT(*) > 1"
    ).fetchall()
    if duplicate_psks:
        logging.warning(
            "Duplicate channel PSK values found; using non-unique PSK index: %s",
            [row[0] for row in duplicate_psks],
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_channels_psk ON channels(psk)")
    else:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_psk ON channels(psk)")


def _ensure_database_indexes(c):
    _ensure_sys_config_indexes(c)
    _ensure_channels_indexes(c)
    index_statements = (
        "CREATE INDEX IF NOT EXISTS idx_bulletins_unique_id ON bulletins(unique_id)",
        "CREATE INDEX IF NOT EXISTS idx_bulletins_synced_deleted ON bulletins(synced, deleted)",
        "CREATE INDEX IF NOT EXISTS idx_bulletins_delete_reconcile ON bulletins(delete_reconcile)",
        "CREATE INDEX IF NOT EXISTS idx_bulletins_board_deleted ON bulletins(board, deleted)",
        "CREATE INDEX IF NOT EXISTS idx_mail_unique_id ON mail(unique_id)",
        "CREATE INDEX IF NOT EXISTS idx_mail_recipient ON mail(recipient)",
        "CREATE INDEX IF NOT EXISTS idx_mail_recipient_short_name ON mail(recipient_short_name)",
        "CREATE INDEX IF NOT EXISTS idx_mail_synced ON mail(synced)",
        "CREATE INDEX IF NOT EXISTS idx_mail_read ON mail(read)",
        "CREATE INDEX IF NOT EXISTS idx_channels_synced ON channels(synced)",
        "CREATE INDEX IF NOT EXISTS idx_channels_publish ON channels(publish)",
        "CREATE INDEX IF NOT EXISTS idx_channels_deleted ON channels(deleted)",
        "CREATE INDEX IF NOT EXISTS idx_channels_delete_reconcile ON channels(delete_reconcile)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sysadmin_nodes_node ON sysadmin_nodes(node_hex_username)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_node_catalog_node ON node_catalog(node_hex_username)",
        "CREATE INDEX IF NOT EXISTS idx_node_catalog_short_name ON node_catalog(short_name)",
        "CREATE INDEX IF NOT EXISTS idx_sync_peers_protocol ON sync_peers(sync_protocol)",
        "CREATE INDEX IF NOT EXISTS idx_record_sync_peers_pending "
        "ON record_sync_peers(record_type, record_key, synced)",
        "CREATE INDEX IF NOT EXISTS idx_mesh_nodes_short_name ON mesh_nodes(short_name)",
        "CREATE INDEX IF NOT EXISTS idx_mesh_nodes_last_heard ON mesh_nodes(last_heard)",
    )
    for statement in index_statements:
        c.execute(statement)


def _ensure_sys_config_indexes(c):
    # PK (cfg_section, cfg_key) handles point lookups and updates.
    # Covering index avoids table lookups for full-table list/export reads.
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_sys_config_section_key_value "
        "ON sys_config(cfg_section, cfg_key, cfg_value)"
    )
    c.execute("ANALYZE sys_config")


def upsert_mesh_node(node_id, short_name=None, long_name=None, last_heard=None, from_sync=False):
    node_id = (node_id or "").strip()
    if not node_id:
        return False
    short_name = (short_name or "").strip() or None
    long_name = (long_name or "").strip() or None
    if last_heard is not None:
        try:
            last_heard = int(last_heard)
        except (TypeError, ValueError):
            last_heard = None

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT short_name, long_name, last_heard FROM mesh_nodes WHERE node_id = ?",
        (node_id,),
    )
    existing = c.fetchone()

    current_time = int(time.time())
    if existing:
        old_sn, old_ln, old_lh = existing
        new_sn = short_name or old_sn
        new_ln = long_name or old_ln
        if from_sync and old_lh is not None and last_heard is not None:
            new_lh = max(int(last_heard), int(old_lh))
        else:
            new_lh = last_heard if last_heard is not None else old_lh
    else:
        new_sn, new_ln = short_name, long_name
        new_lh = last_heard if last_heard is not None else current_time

    changed = (
        existing is None
        or new_sn != existing[0]
        or new_ln != existing[1]
        or new_lh != existing[2]
    )
    if from_sync and existing and not changed:
        return False

    c.execute(
        """INSERT INTO mesh_nodes (node_id, short_name, long_name, last_heard, last_updated)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(node_id) DO UPDATE SET
             short_name=excluded.short_name,
             long_name=excluded.long_name,
             last_heard=excluded.last_heard,
             last_updated=excluded.last_updated""",
        (node_id, new_sn, new_ln, new_lh, current_time),
    )
    conn.commit()
    if changed and not from_sync:
        _invalidate_mesh_node_sync(node_id)
    return changed


def lookup_mesh_nodes_by_short_name(short_name):
    short_name = (short_name or "").strip()
    if not short_name:
        return []
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT node_id, short_name, long_name FROM mesh_nodes "
        "WHERE short_name = ? COLLATE NOCASE",
        (short_name,),
    )
    return [
        {
            "num": node_id,
            "shortName": name or node_id,
            "longName": long_name or name or node_id,
        }
        for node_id, name, long_name in c.fetchall()
    ]


def lookup_catalog_nodes_by_short_name(short_name):
    short_name = (short_name or "").strip()
    if not short_name:
        return []
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT node_hex_username, short_name, long_name FROM node_catalog "
        "WHERE short_name = ? COLLATE NOCASE",
        (short_name,),
    )
    return [
        {
            "num": node_hex,
            "shortName": catalog_short or node_hex,
            "longName": long_name or catalog_short or node_hex,
        }
        for node_hex, catalog_short, long_name in c.fetchall()
    ]


def get_mesh_nodes_for_sync():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT node_id, short_name, long_name, last_heard FROM mesh_nodes ORDER BY node_id"
    )
    return c.fetchall()


def _invalidate_mesh_node_sync(node_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM record_sync_peers WHERE record_type = ? AND record_key = ?",
        ("mesh_nodes", node_id),
    )
    conn.commit()


def _mesh_node_synced_to_peer(node_id, peer_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM record_sync_peers "
        "WHERE record_type = ? AND record_key = ? AND peer_id = ? AND synced = 'Y'",
        ("mesh_nodes", node_id, peer_id),
    )
    return c.fetchone() is not None


def _mark_mesh_node_synced_to_peer(node_id, peer_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO record_sync_peers (record_type, record_key, peer_id, synced) "
        "VALUES (?, ?, ?, 'Y') "
        "ON CONFLICT(record_type, record_key, peer_id) DO UPDATE SET synced = 'Y'",
        ("mesh_nodes", node_id, peer_id),
    )
    conn.commit()


def sync_mesh_nodes_to_peers(sync_peers, interface):
    from .utils import filter_peers_for_record_type, send_mesh_node_to_peer, sync_peer_protocol
    from .sync_wire import is_rs_sync_protocol

    peers = get_sync_peers_from_interface(interface, sync_peers)
    mesh_peers = [
        peer for peer in filter_peers_for_record_type(peers, 'mesh_nodes')
        if is_rs_sync_protocol(sync_peer_protocol(peer))
    ]
    if not mesh_peers:
        return

    for node_id, short_name, long_name, last_heard in get_mesh_nodes_for_sync():
        for peer in mesh_peers:
            peer_id = _resolve_peer_id(peer)
            if peer_id is None or _mesh_node_synced_to_peer(node_id, peer_id):
                continue
            if send_mesh_node_to_peer(
                node_id, short_name, long_name, last_heard, peer, interface,
            ):
                _mark_mesh_node_synced_to_peer(node_id, peer_id)


def ingest_mesh_node_sync(node_id, short_name, long_name, last_heard, sender_node_id=None):
    upsert_mesh_node(
        node_id,
        short_name,
        long_name,
        last_heard,
        from_sync=True,
    )
    peer_id = _peer_id_for_bbs_node(sender_node_id)
    if peer_id is not None:
        _mark_mesh_node_synced_to_peer(node_id, peer_id)


def get_all_mesh_nodes():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT node_id, short_name, long_name, last_heard, last_updated "
        "FROM mesh_nodes ORDER BY short_name COLLATE NOCASE, node_id"
    )
    return c.fetchall()


def get_mesh_node(node_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT node_id, short_name, long_name, last_heard, last_updated "
        "FROM mesh_nodes WHERE node_id = ?",
        (node_id,),
    )
    return c.fetchone()


def add_mesh_node(node_id, short_name=None, long_name=None, last_heard=None):
    node_id = (node_id or "").strip()
    if not node_id:
        return False
    upsert_mesh_node(node_id, short_name, long_name, last_heard)
    return True


def update_mesh_node(node_id, short_name=None, long_name=None, last_heard=None):
    if get_mesh_node(node_id) is None:
        return False
    upsert_mesh_node(node_id, short_name, long_name, last_heard)
    return True


def delete_mesh_node(node_id):
    node_id = (node_id or "").strip()
    if not node_id:
        return False
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM mesh_nodes WHERE node_id = ?", (node_id,))
    deleted = c.rowcount > 0
    if deleted:
        c.execute(
            "DELETE FROM record_sync_peers WHERE record_type = ? AND record_key = ?",
            ("mesh_nodes", node_id),
        )
    conn.commit()
    return deleted


def purge_mesh_nodes():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM mesh_nodes")
    c.execute("DELETE FROM record_sync_peers WHERE record_type = ?", ("mesh_nodes",))
    conn.commit()


MESH_NODE_CSV_FIELDS = ("node_id", "short_name", "long_name", "last_heard")


def export_mesh_nodes_to_csv(file_path):
    conn = get_db_connection()
    c = conn.cursor()
    columns = ", ".join(MESH_NODE_CSV_FIELDS)
    rows = c.execute(
        f"SELECT {columns} FROM mesh_nodes ORDER BY short_name COLLATE NOCASE, node_id"
    ).fetchall()
    with open(file_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MESH_NODE_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(zip(MESH_NODE_CSV_FIELDS, row)))
    return len(rows)


def import_mesh_nodes_from_csv(file_path, replace=False):
    with open(file_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV file is missing a header row.")
        missing = [field for field in MESH_NODE_CSV_FIELDS if field not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

        conn = get_db_connection()
        c = conn.cursor()
        if replace:
            c.execute("DELETE FROM mesh_nodes")
            c.execute("DELETE FROM record_sync_peers WHERE record_type = ?", ("mesh_nodes",))
        inserted = updated = unchanged = 0
        errors = []
        for line_number, row in enumerate(reader, start=2):
            node_id = (row.get("node_id") or "").strip()
            if not node_id:
                errors.append(f"Line {line_number}: node_id is required.")
                continue
            short_name = (row.get("short_name") or "").strip() or None
            long_name = (row.get("long_name") or "").strip() or None
            last_heard_raw = (row.get("last_heard") or "").strip()
            last_heard = None
            if last_heard_raw:
                try:
                    last_heard = int(last_heard_raw)
                except ValueError:
                    errors.append(f"Line {line_number}: invalid last_heard value.")
                    continue
            existing = get_mesh_node(node_id)
            if existing is None:
                upsert_mesh_node(node_id, short_name, long_name, last_heard)
                inserted += 1
                continue
            _, old_short, old_long, old_heard, _ = existing
            if (old_short, old_long, old_heard) == (short_name, long_name, last_heard):
                unchanged += 1
                continue
            upsert_mesh_node(node_id, short_name, long_name, last_heard)
            updated += 1
        conn.commit()
    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "errors": errors,
    }


def _default_sync_mesh_nodes(sync_protocol):
    return 'Y' if sync_protocol == 'rsv1' else 'N'


def _apply_sync_mesh_nodes_for_protocol(sync_protocol, sync_mesh_nodes=None):
    if sync_protocol == 'tc2':
        return 'N'
    if sync_mesh_nodes is None:
        return 'Y'
    return _normalize_sync_flag(sync_mesh_nodes)


def _normalize_sync_protocol(protocol):
    protocol = (protocol or 'tc2').strip().lower()
    return protocol if protocol in SYNC_PROTOCOLS else None


def ensure_sys_config_from_yaml(config_file=None):
    config_file = config_file or DEFAULT_CONFIG_FILE
    config = load_config(config_file)
    entries = flatten_yaml_config(config)

    conn = get_db_connection()
    c = conn.cursor()
    for cfg_section, cfg_key, cfg_value in entries:
        c.execute(
            "SELECT 1 FROM sys_config WHERE cfg_section = ? AND cfg_key = ?",
            (cfg_section, cfg_key)
        )
        if c.fetchone() is None:
            c.execute(
                "INSERT INTO sys_config (cfg_section, cfg_key, cfg_value) VALUES (?, ?, ?)",
                (cfg_section, cfg_key, cfg_value)
            )
    conn.commit()


SCHEDULE_CONFIG_DEFAULTS = {
    'peer_sync_minutes': '5',
    'module_exec_minutes': '1',
    'sync_purge_minutes': '5',
    'bulletin_display_age_days': '30',
}


def get_sys_config_value(cfg_section, cfg_key, default=None):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT cfg_value FROM sys_config WHERE cfg_section = ? AND cfg_key = ?",
        (cfg_section, cfg_key),
    )
    row = c.fetchone()
    return row[0] if row else default


def _get_schedule_minutes(cfg_key):
    value = get_sys_config_value('schedule', cfg_key)
    default = SCHEDULE_CONFIG_DEFAULTS[cfg_key]
    try:
        minutes = int(str(value).strip()) if value is not None else int(default)
    except (TypeError, ValueError):
        minutes = int(default)
    if minutes < 1:
        minutes = int(default)
    return minutes


def get_peer_sync_seconds():
    return _get_schedule_minutes('peer_sync_minutes') * 60


def get_sync_purge_seconds():
    return _get_schedule_minutes('sync_purge_minutes') * 60


def get_module_exec_seconds():
    return _get_schedule_minutes('module_exec_minutes') * 60


def get_bulletin_display_age_days():
    value = get_sys_config_value('schedule', 'bulletin_display_age_days')
    default = SCHEDULE_CONFIG_DEFAULTS['bulletin_display_age_days']
    try:
        days = int(str(value).strip()) if value is not None else int(default)
    except (TypeError, ValueError):
        days = int(default)
    if days < 0:
        days = int(default)
    return days


def _bulletin_mesh_cutoff_date():
    age_days = get_bulletin_display_age_days()
    return (datetime.now() - timedelta(days=age_days)).strftime('%Y-%m-%d %H:%M')


def _ensure_default_modules(c):
    c.execute(
        "INSERT OR IGNORE INTO modules "
        "(module_name, module_dir, menu_option, enabled, schedule_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ('Node Info', 'node_info', 'I', 'Y', 'Y'),
    )
    c.execute(
        "INSERT OR IGNORE INTO modules "
        "(module_name, module_dir, menu_option, enabled, schedule_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ('Example Hello', 'example_hello', 'E', 'N', 'N'),
    )
    c.execute(
        "INSERT OR IGNORE INTO modules "
        "(module_name, module_dir, menu_option, enabled, schedule_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ('Fortune', 'fortune', 'F', 'Y', 'N'),
    )


def format_module_menu_option(menu_option):
    text = (menu_option or '').strip()
    if len(text) == 1 and text.isalpha():
        return text.upper()
    return text


def _normalize_module_row(row):
    if row is None:
        return None
    menu_option = format_module_menu_option(row[3])
    if menu_option == row[3]:
        return row
    return (row[0], row[1], row[2], menu_option, row[4], row[5])


def get_modules(enabled_only=False):
    conn = get_db_connection()
    c = conn.cursor()
    if enabled_only:
        c.execute(
            "SELECT id, module_name, module_dir, menu_option, enabled, schedule_enabled "
            "FROM modules WHERE enabled = 'Y' ORDER BY id"
        )
    else:
        c.execute(
            "SELECT id, module_name, module_dir, menu_option, enabled, schedule_enabled "
            "FROM modules ORDER BY id"
        )
    return [_normalize_module_row(row) for row in c.fetchall()]


def get_module_by_id(module_id):
    try:
        module_id = int(module_id)
    except (TypeError, ValueError):
        return None
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, module_name, module_dir, menu_option, enabled, schedule_enabled "
        "FROM modules WHERE id = ?",
        (module_id,),
    )
    return _normalize_module_row(c.fetchone())


def get_module_by_menu_option(menu_option):
    menu_option = format_module_menu_option((menu_option or '').strip())
    if not menu_option:
        return None
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, module_name, module_dir, menu_option, enabled, schedule_enabled "
        "FROM modules WHERE menu_option = ? COLLATE NOCASE",
        (menu_option,),
    )
    return _normalize_module_row(c.fetchone())


def update_module_flags(module_id, enabled=None, schedule_enabled=None):
    try:
        module_id = int(module_id)
    except (TypeError, ValueError):
        return False
    conn = get_db_connection()
    c = conn.cursor()
    if enabled is not None:
        c.execute(
            "UPDATE modules SET enabled = ? WHERE id = ?",
            (_normalize_sync_flag(enabled), module_id),
        )
    if schedule_enabled is not None:
        c.execute(
            "UPDATE modules SET schedule_enabled = ? WHERE id = ?",
            (_normalize_sync_flag(schedule_enabled), module_id),
        )
    conn.commit()
    return True


DEFAULT_EVENTBUS_TOPIC = 'meshtastic.receive'


def get_eventbus_topic():
    value = get_sys_config_value(
        'bbs',
        'eventbus_topic',
        DEFAULT_EVENTBUS_TOPIC,
    )
    text = str(value).strip() if value is not None else ''
    return text or DEFAULT_EVENTBUS_TOPIC


def get_sys_config_entries():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT cfg_section, cfg_key, cfg_value FROM sys_config "
        "ORDER BY cfg_section, cfg_key"
    )
    return c.fetchall()


def add_sys_config_entry(cfg_section, cfg_key, cfg_value):
    cfg_section = (cfg_section or '').strip()
    cfg_key = (cfg_key or '').strip()
    if not cfg_section or not cfg_key:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO sys_config (cfg_section, cfg_key, cfg_value) VALUES (?, ?, ?)",
            (cfg_section, cfg_key, cfg_value)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def update_sys_config_entry(cfg_section, cfg_key, cfg_value):
    cfg_section = (cfg_section or '').strip()
    cfg_key = (cfg_key or '').strip()
    if not cfg_section or not cfg_key:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE sys_config SET cfg_value = ? WHERE cfg_section = ? AND cfg_key = ?",
        (cfg_value, cfg_section, cfg_key)
    )
    conn.commit()
    return c.rowcount > 0


def delete_sys_config_entry(cfg_section, cfg_key):
    cfg_section = (cfg_section or '').strip()
    cfg_key = (cfg_key or '').strip()
    if not cfg_section or not cfg_key:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM sys_config WHERE cfg_section = ? AND cfg_key = ?",
        (cfg_section, cfg_key)
    )
    conn.commit()
    return c.rowcount > 0


def get_sysadmin_nodes():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, short_name, node_hex_username FROM sysadmin_nodes ORDER BY id"
    )
    return c.fetchall()


def add_sysadmin_node(short_name, node_hex_username):
    short_name = (short_name or '').strip()
    node_hex_username = (node_hex_username or '').strip()
    if not short_name or not node_hex_username:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM sysadmin_nodes WHERE node_hex_username = ?",
        (node_hex_username,)
    )
    if c.fetchone():
        return False
    c.execute(
        "INSERT INTO sysadmin_nodes (short_name, node_hex_username) VALUES (?, ?)",
        (short_name, node_hex_username)
    )
    conn.commit()
    sync_catalog_bbs_admin_for_sysadmin(node_hex_username, True)
    return True


def update_sysadmin_node(node_id, short_name, node_hex_username):
    short_name = (short_name or '').strip()
    node_hex_username = (node_hex_username or '').strip()
    if not node_id or not short_name or not node_hex_username:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT node_hex_username FROM sysadmin_nodes WHERE id = ?", (node_id,))
    current = c.fetchone()
    if not current:
        return False
    old_node_hex_username = current[0]
    c.execute(
        "SELECT 1 FROM sysadmin_nodes WHERE node_hex_username = ? AND id != ?",
        (node_hex_username, node_id),
    )
    if c.fetchone():
        return False
    c.execute(
        "UPDATE sysadmin_nodes SET short_name = ?, node_hex_username = ? WHERE id = ?",
        (short_name, node_hex_username, node_id),
    )
    if c.rowcount == 0:
        conn.commit()
        return False
    conn.commit()
    if old_node_hex_username != node_hex_username:
        sync_catalog_bbs_admin_for_sysadmin(old_node_hex_username, False)
    sync_catalog_bbs_admin_for_sysadmin(node_hex_username, True)
    return True


def delete_sysadmin_node(node_id):
    if not node_id:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT node_hex_username FROM sysadmin_nodes WHERE id = ?", (node_id,))
    current = c.fetchone()
    if not current:
        return False
    node_hex_username = current[0]
    c.execute("DELETE FROM sysadmin_nodes WHERE id = ?", (node_id,))
    if c.rowcount == 0:
        conn.commit()
        return False
    conn.commit()
    sync_catalog_bbs_admin_for_sysadmin(node_hex_username, False)
    return True


def get_sync_peers(protocol=None):
    conn = get_db_connection()
    c = conn.cursor()
    if protocol:
        normalized = _normalize_sync_protocol(protocol)
        if not normalized:
            return []
        c.execute(
            f"SELECT {PEER_ROW_SELECT} FROM sync_peers WHERE sync_protocol = ? ORDER BY id",
            (normalized,)
        )
    else:
        c.execute(f"SELECT {PEER_ROW_SELECT} FROM sync_peers ORDER BY id")
    return c.fetchall()


def reload_sync_peers(interface):
    """Refresh in-memory sync peer cache from the database."""
    sync_peers = get_sync_peers()
    if interface is not None:
        interface.sync_peers = sync_peers
        interface.bbs_nodes = [row[1] for row in sync_peers]
    return sync_peers


def reload_admin_nodes(interface):
    """Refresh in-memory sysadmin cache from the database."""
    admin_nodes = get_admin_nodes()
    if interface is not None:
        interface.admin_nodes = admin_nodes
    return admin_nodes


def normalize_sync_peer_last_heard(last_heard):
    return int(last_heard) if last_heard is not None else int(time.time())


def backfill_sync_peer_last_heard():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE sync_peers SET last_heard = ? WHERE last_heard IS NULL",
        (int(time.time()),)
    )
    conn.commit()


def touch_sync_peer_last_heard(bbs_node):
    bbs_node = (bbs_node or '').strip()
    if not bbs_node:
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE sync_peers SET last_heard = ? WHERE bbs_node = ?",
        (int(time.time()), bbs_node)
    )
    conn.commit()


def get_sync_peer_nodes(protocol='tc2'):
    return [row[1] for row in get_sync_peers(protocol)]


def add_sync_peer(
    bbs_node,
    sync_protocol='tc2',
    bbs_name=None,
    sync_bulletins='Y',
    sync_mail='Y',
    sync_channels='Y',
    sync_mesh_nodes=None,
    ingest_bulletins='Y',
    ingest_channels='Y',
    enabled='Y',
):
    bbs_node = (bbs_node or '').strip()
    bbs_name = (bbs_name or '').strip() or None
    sync_protocol = _normalize_sync_protocol(sync_protocol)
    sync_bulletins = _normalize_sync_flag(sync_bulletins)
    sync_mail = _normalize_sync_flag(sync_mail)
    sync_channels = _normalize_sync_flag(sync_channels)
    sync_mesh_nodes = _apply_sync_mesh_nodes_for_protocol(sync_protocol, sync_mesh_nodes)
    ingest_bulletins = _normalize_sync_flag(ingest_bulletins)
    ingest_channels = _normalize_sync_flag(ingest_channels)
    enabled = _normalize_sync_flag(enabled)
    if not bbs_node or not sync_protocol:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO sync_peers "
            "(bbs_node, bbs_name, sync_protocol, last_heard, sync_bulletins, sync_mail, sync_channels, "
            "sync_mesh_nodes, ingest_bulletins, ingest_channels, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                bbs_node, bbs_name, sync_protocol, int(time.time()),
                sync_bulletins, sync_mail, sync_channels, sync_mesh_nodes,
                ingest_bulletins, ingest_channels, enabled,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def _clear_peer_record_sync(peer_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM record_sync_peers WHERE peer_id = ?", (peer_id,))
    conn.commit()


def _clear_disabled_peer_sync_state(peer_id, sync_bulletins, sync_mail, sync_channels, sync_mesh_nodes='Y'):
    disabled_types = []
    if sync_bulletins == 'N':
        disabled_types.append('bulletins')
    if sync_mail == 'N':
        disabled_types.append('mail')
    if sync_channels == 'N':
        disabled_types.append('channels')
    if sync_mesh_nodes == 'N':
        disabled_types.append('mesh_nodes')
    if not disabled_types:
        return

    conn = get_db_connection()
    c = conn.cursor()
    for record_type in disabled_types:
        c.execute(
            "DELETE FROM record_sync_peers WHERE peer_id = ? AND record_type = ?",
            (peer_id, record_type),
        )
    conn.commit()


def update_sync_peer(
    peer_id,
    bbs_node,
    sync_protocol,
    bbs_name=None,
    sync_bulletins='Y',
    sync_mail='Y',
    sync_channels='Y',
    sync_mesh_nodes=None,
    ingest_bulletins='Y',
    ingest_channels='Y',
    enabled='Y',
):
    bbs_node = (bbs_node or '').strip()
    bbs_name = (bbs_name or '').strip() or None
    sync_protocol = _normalize_sync_protocol(sync_protocol)
    sync_bulletins = _normalize_sync_flag(sync_bulletins)
    sync_mail = _normalize_sync_flag(sync_mail)
    sync_channels = _normalize_sync_flag(sync_channels)
    sync_mesh_nodes = _apply_sync_mesh_nodes_for_protocol(sync_protocol, sync_mesh_nodes)
    ingest_bulletins = _normalize_sync_flag(ingest_bulletins)
    ingest_channels = _normalize_sync_flag(ingest_channels)
    enabled = _normalize_sync_flag(enabled)
    if not peer_id or not bbs_node or not sync_protocol:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "UPDATE sync_peers SET bbs_node = ?, bbs_name = ?, sync_protocol = ?, last_heard = ?, "
            "sync_bulletins = ?, sync_mail = ?, sync_channels = ?, sync_mesh_nodes = ?, "
            "ingest_bulletins = ?, ingest_channels = ?, enabled = ?, rs_version_alert = 'N', "
            "rs_wire_version_seen = NULL WHERE id = ?",
            (
                bbs_node, bbs_name, sync_protocol, int(time.time()),
                sync_bulletins, sync_mail, sync_channels, sync_mesh_nodes,
                ingest_bulletins, ingest_channels, enabled, peer_id,
            ),
        )
        conn.commit()
        if c.rowcount > 0:
            if enabled == 'N':
                _clear_peer_record_sync(peer_id)
            else:
                _clear_disabled_peer_sync_state(
                    peer_id, sync_bulletins, sync_mail, sync_channels, sync_mesh_nodes,
                )
            _refresh_all_aggregate_synced()
        return c.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def delete_sync_peer(peer_id):
    if not peer_id:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sync_peers WHERE id = ?", (peer_id,))
    deleted = c.rowcount > 0
    conn.commit()
    if deleted:
        _refresh_all_aggregate_synced()
    return deleted

def add_channel(
    name,
    psk,
    bbs_nodes=None,
    interface=None,
    from_sync=False,
    unique_id=None,
    defer_sync=False,
    publish=None,
):
    if not unique_id:
        unique_id = str(uuid.uuid4())

    if publish is None:
        publish = 'N' if from_sync else 'Y'
    publish = (publish or 'N').strip().upper()
    if publish not in ('Y', 'N'):
        publish = 'N'

    conn = get_db_connection()
    c = conn.cursor()

    if from_sync:
        if unique_id:
            c.execute(
                "SELECT id FROM channels WHERE unique_id = ? AND deleted = 'N'",
                (unique_id,),
            )
            existing = c.fetchone()
            if existing:
                logging.info(
                    f"Channel with unique_id {unique_id} already exists; skipping duplicate ingest."
                )
                return existing[0]
        c.execute("SELECT id FROM channels WHERE psk = ? AND deleted = 'N'", (psk,))
        existing = c.fetchone()
        if existing:
            logging.info("Channel with matching PSK already exists; skipping duplicate ingest.")
            return existing[0]

    synced = 'Y' if from_sync else 'N'
    try:
        c.execute(
            "INSERT INTO channels (name, psk, publish, synced, unique_id) VALUES (?, ?, ?, ?, ?)",
            (name, psk, publish, synced, unique_id),
        )
    except sqlite3.IntegrityError:
        c.execute(
            "SELECT id FROM channels WHERE unique_id = ? OR psk = ?",
            (unique_id, psk),
        )
        existing = c.fetchone()
        if existing:
            logging.info("Channel already exists; skipping duplicate ingest.")
            return existing[0]
        raise
    conn.commit()
    channel_id = c.lastrowid

    if from_sync:
        _mark_inbound_sync_complete('channels', unique_id)
        return channel_id

    if not defer_sync:
        sync_channel_record(unique_id, bbs_nodes, interface)

    return channel_id


def sync_channel_record(unique_id, bbs_nodes, interface):
    if interface is None:
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, psk FROM channels WHERE unique_id = ? AND deleted = 'N'", (unique_id,))
    row = c.fetchone()
    if row is None:
        return

    name, psk = row

    def _send(pending_peers):
        return send_channel_to_bbs_nodes(name, psk, pending_peers, interface, unique_id=unique_id)

    _complete_local_sync('channels', 'unique_id', unique_id, unique_id, bbs_nodes, interface, _send)


def ensure_superuser_sysadmin(superuser_node):
    if not superuser_node or not superuser_node.strip():
        return False, None

    superuser_node = superuser_node.strip()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT 1 FROM sysadmin_nodes WHERE node_hex_username = ?", (superuser_node,))
    if c.fetchone():
        return False, None

    short_name = superuser_node[-4:] if len(superuser_node) >= 4 else superuser_node
    c.execute(
        "INSERT INTO sysadmin_nodes (short_name, node_hex_username) VALUES (?, ?)",
        (short_name, superuser_node)
    )
    conn.commit()
    sync_catalog_bbs_admin_for_sysadmin(superuser_node, True)
    return True, short_name


def get_admin_nodes():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT node_hex_username FROM sysadmin_nodes")
    admin_nodes = []
    for row in c.fetchall():
        node_id = row[0].strip() if row[0] else ''
        if node_id and node_id not in admin_nodes:
            admin_nodes.append(node_id)

    return admin_nodes


def sync_sysadmin_for_catalog_entry(short_name, node_hex_username, bbs_admin):
    conn = get_db_connection()
    c = conn.cursor()
    if (bbs_admin or 'N').upper() == 'Y':
        c.execute("DELETE FROM sysadmin_nodes WHERE node_hex_username = ?", (node_hex_username,))
        c.execute(
            "INSERT INTO sysadmin_nodes (short_name, node_hex_username) VALUES (?, ?)",
            (short_name, node_hex_username)
        )
    else:
        c.execute("DELETE FROM sysadmin_nodes WHERE node_hex_username = ?", (node_hex_username,))
    conn.commit()


def sync_catalog_bbs_admin_for_sysadmin(node_hex_username, is_sysadmin):
    node_hex_username = (node_hex_username or '').strip()
    if not node_hex_username:
        return

    conn = get_db_connection()
    c = conn.cursor()
    flag = 'Y' if is_sysadmin else 'N'
    updated = current_catalog_timestamp()
    c.execute(
        "UPDATE node_catalog SET bbs_admin = ?, updated = ? WHERE node_hex_username = ?",
        (flag, updated, node_hex_username),
    )
    conn.commit()


NODE_CATALOG_CSV_FIELDS = (
    'long_name',
    'short_name',
    'node_hex_username',
    'mesh_admin',
    'bbs_admin',
    'bbs_mail_forward_to',
    'has_gps',
    'public_key',
    'private_key',
    'ble_pin',
    'hardware',
    'comment',
    'created',
    'updated',
)

NODE_CATALOG_REQUIRED_CSV_FIELDS = (
    'long_name',
    'short_name',
    'node_hex_username',
    'public_key',
)


def _normalize_node_catalog_csv_value(field, value):
    if field in ('bbs_mail_forward_to', 'private_key', 'hardware', 'comment'):
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    if field in ('mesh_admin', 'bbs_admin', 'has_gps'):
        text = (value or 'N').strip().upper()
        return text if text in ('Y', 'N') else 'N'
    if field == 'ble_pin':
        text = (value or '123456').strip()
        return text or '123456'
    if value is None:
        return ''
    return str(value).strip()


def _parse_node_catalog_csv_row(row_dict):
    return {
        field: _normalize_node_catalog_csv_value(field, row_dict.get(field))
        for field in NODE_CATALOG_CSV_FIELDS
    }


def _validate_node_catalog_csv_headers(fieldnames):
    if not fieldnames:
        raise ValueError('CSV file has no header row.')
    headers = {name.strip() for name in fieldnames if name and name.strip()}
    missing = [field for field in NODE_CATALOG_CSV_FIELDS if field not in headers]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")


def _validate_node_catalog_row(parsed):
    missing = [field for field in NODE_CATALOG_REQUIRED_CSV_FIELDS if not parsed.get(field)]
    if missing:
        raise ValueError(f"Missing required value(s): {', '.join(missing)}")


def _node_catalog_row_differs(existing, parsed):
    for field in NODE_CATALOG_CSV_FIELDS:
        existing_value = _normalize_node_catalog_csv_value(field, existing.get(field))
        parsed_value = _normalize_node_catalog_csv_value(field, parsed.get(field))
        if existing_value != parsed_value:
            return True
    return False


def _catalog_row_to_dict(row):
    return dict(zip(NODE_CATALOG_CSV_FIELDS, row))


def _insert_node_catalog_row(c, parsed):
    now = current_catalog_timestamp()
    if not parsed['created']:
        parsed['created'] = now
    if not parsed['updated']:
        parsed['updated'] = now
    values = tuple(parsed[field] for field in NODE_CATALOG_CSV_FIELDS)
    columns = ', '.join(NODE_CATALOG_CSV_FIELDS)
    placeholders = ', '.join('?' for _ in NODE_CATALOG_CSV_FIELDS)
    c.execute(
        f"INSERT INTO node_catalog ({columns}) VALUES ({placeholders})",
        values,
    )


def _update_node_catalog_row(c, parsed, existing=None):
    parsed = dict(parsed)
    if existing and not parsed['created']:
        parsed['created'] = existing['created']
    parsed['updated'] = current_catalog_timestamp()
    assignments = ', '.join(f"{field} = ?" for field in NODE_CATALOG_CSV_FIELDS)
    values = tuple(parsed[field] for field in NODE_CATALOG_CSV_FIELDS)
    values += (parsed['node_hex_username'],)
    c.execute(
        f"UPDATE node_catalog SET {assignments} WHERE node_hex_username = ?",
        values,
    )


def export_node_catalog_to_csv(file_path):
    conn = get_db_connection()
    c = conn.cursor()
    columns = ', '.join(NODE_CATALOG_CSV_FIELDS)
    c.execute(
        f"SELECT {columns} FROM node_catalog ORDER BY short_name COLLATE NOCASE, id"
    )
    rows = c.fetchall()
    with open(file_path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(NODE_CATALOG_CSV_FIELDS)
        for row in rows:
            writer.writerow('' if value is None else value for value in row)
    return len(rows)


def import_node_catalog_from_csv(file_path, replace=False):
    with open(file_path, 'r', newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        _validate_node_catalog_csv_headers(reader.fieldnames)
        parsed_rows = []
        seen_nodes = set()
        errors = []
        for line_number, row in enumerate(reader, start=2):
            if not row or not any((value or '').strip() for value in row.values()):
                continue
            parsed = _parse_node_catalog_csv_row(row)
            node_hex_username = parsed['node_hex_username']
            try:
                _validate_node_catalog_row(parsed)
            except ValueError as exc:
                errors.append(f"Line {line_number}: {exc}")
                continue
            if node_hex_username in seen_nodes:
                errors.append(f"Line {line_number}: duplicate node_hex_username {node_hex_username}")
                continue
            seen_nodes.add(node_hex_username)
            parsed_rows.append(parsed)

    conn = get_db_connection()
    c = conn.cursor()
    columns = ', '.join(NODE_CATALOG_CSV_FIELDS)
    existing_rows = {}
    for row in c.execute(f"SELECT {columns} FROM node_catalog").fetchall():
        record = _catalog_row_to_dict(row)
        existing_rows[record['node_hex_username']] = record
    prior_rows = dict(existing_rows)
    old_nodes = set(prior_rows)

    inserted = 0
    updated = 0
    unchanged = 0

    if replace:
        c.execute("DELETE FROM node_catalog")
        conn.commit()
        existing_rows = {}

    for parsed in parsed_rows:
        node_hex_username = parsed['node_hex_username']
        existing = existing_rows.get(node_hex_username)
        if existing is None:
            _insert_node_catalog_row(c, parsed)
            inserted += 1
            continue
        if not _node_catalog_row_differs(existing, parsed):
            unchanged += 1
            continue
        _update_node_catalog_row(c, parsed, existing)
        updated += 1

    conn.commit()

    imported_nodes = {parsed['node_hex_username'] for parsed in parsed_rows}
    if replace:
        for node_hex_username in old_nodes - imported_nodes:
            sync_sysadmin_for_catalog_entry('', node_hex_username, 'N')
        for parsed in parsed_rows:
            sync_sysadmin_for_catalog_entry(
                parsed['short_name'], parsed['node_hex_username'], parsed['bbs_admin'],
            )
    else:
        for parsed in parsed_rows:
            node_hex_username = parsed['node_hex_username']
            prior = prior_rows.get(node_hex_username)
            if prior is None or _node_catalog_row_differs(prior, parsed):
                sync_sysadmin_for_catalog_entry(
                    parsed['short_name'], node_hex_username, parsed['bbs_admin'],
                )

    return {
        'inserted': inserted,
        'updated': updated,
        'unchanged': unchanged,
        'errors': errors,
    }


CHANNEL_CSV_FIELDS = (
    'name',
    'psk',
    'publish',
    'synced',
    'unique_id',
)

CHANNEL_REQUIRED_CSV_FIELDS = (
    'name',
    'psk',
)


def _normalize_channel_csv_value(field, value):
    if field in ('publish', 'synced'):
        text = (value or ('Y' if field == 'publish' else 'N')).strip().upper()
        return text if text in ('Y', 'N') else ('Y' if field == 'publish' else 'N')
    if value is None:
        return ''
    return str(value).strip()


def _parse_channel_csv_row(row_dict):
    return {
        field: _normalize_channel_csv_value(field, row_dict.get(field))
        for field in CHANNEL_CSV_FIELDS
    }


def _validate_channel_csv_headers(fieldnames):
    if not fieldnames:
        raise ValueError('CSV file has no header row.')
    headers = {name.strip() for name in fieldnames if name and name.strip()}
    missing = [field for field in CHANNEL_CSV_FIELDS if field not in headers]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")


def _validate_channel_row(parsed):
    missing = [field for field in CHANNEL_REQUIRED_CSV_FIELDS if not parsed.get(field)]
    if missing:
        raise ValueError(f"Missing required value(s): {', '.join(missing)}")


def _channel_row_differs(existing, parsed):
    for field in CHANNEL_CSV_FIELDS:
        existing_value = _normalize_channel_csv_value(field, existing.get(field))
        parsed_value = _normalize_channel_csv_value(field, parsed.get(field))
        if existing_value != parsed_value:
            return True
    return False


def _channel_row_to_dict(row):
    return dict(zip(CHANNEL_CSV_FIELDS, row))


def _channel_synced_value_for_import(parsed, changed=False):
    publish = parsed.get('publish') or 'Y'
    if publish != 'Y':
        return 'Y'
    if changed:
        return 'N'
    synced = (parsed.get('synced') or 'N').strip().upper()
    return synced if synced in ('Y', 'N') else 'N'


def _insert_channel_row(c, parsed):
    parsed = dict(parsed)
    if not parsed['unique_id']:
        parsed['unique_id'] = str(uuid.uuid4())
    parsed['synced'] = _channel_synced_value_for_import(parsed)
    values = tuple(parsed[field] for field in CHANNEL_CSV_FIELDS)
    columns = ', '.join(CHANNEL_CSV_FIELDS)
    placeholders = ', '.join('?' for _ in CHANNEL_CSV_FIELDS)
    c.execute(
        f"INSERT INTO channels ({columns}) VALUES ({placeholders})",
        values,
    )
    return parsed['unique_id']


def _update_channel_row(c, parsed, existing):
    parsed = dict(parsed)
    if not parsed['unique_id']:
        parsed['unique_id'] = existing['unique_id']
    parsed['synced'] = _channel_synced_value_for_import(parsed, changed=True)
    assignments = ', '.join(f"{field} = ?" for field in CHANNEL_CSV_FIELDS)
    values = tuple(parsed[field] for field in CHANNEL_CSV_FIELDS)
    values += (existing['unique_id'],)
    c.execute(
        f"UPDATE channels SET {assignments} WHERE unique_id = ?",
        values,
    )
    return parsed['unique_id']


def _resolve_channel_import_match(parsed, existing_by_unique_id, existing_by_psk):
    unique_id = parsed.get('unique_id')
    if unique_id and unique_id in existing_by_unique_id:
        return unique_id
    psk = parsed.get('psk')
    if psk and psk in existing_by_psk:
        return existing_by_psk[psk]['unique_id']
    return None


def export_channels_to_csv(file_path):
    conn = get_db_connection()
    c = conn.cursor()
    columns = ', '.join(CHANNEL_CSV_FIELDS)
    c.execute(f"SELECT {columns} FROM channels ORDER BY name COLLATE NOCASE, id")
    rows = c.fetchall()
    with open(file_path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(CHANNEL_CSV_FIELDS)
        for row in rows:
            writer.writerow('' if value is None else value for value in row)
    return len(rows)


def import_channels_from_csv(file_path, replace=False):
    with open(file_path, 'r', newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        _validate_channel_csv_headers(reader.fieldnames)
        parsed_rows = []
        seen_unique_ids = set()
        seen_psks = set()
        errors = []
        for line_number, row in enumerate(reader, start=2):
            if not row or not any((value or '').strip() for value in row.values()):
                continue
            parsed = _parse_channel_csv_row(row)
            try:
                _validate_channel_row(parsed)
            except ValueError as exc:
                errors.append(f"Line {line_number}: {exc}")
                continue
            unique_id = parsed['unique_id']
            psk = parsed['psk']
            if unique_id:
                if unique_id in seen_unique_ids:
                    errors.append(f"Line {line_number}: duplicate unique_id {unique_id}")
                    continue
                seen_unique_ids.add(unique_id)
            if psk in seen_psks:
                errors.append(f"Line {line_number}: duplicate psk {psk}")
                continue
            seen_psks.add(psk)
            parsed_rows.append(parsed)

    conn = get_db_connection()
    c = conn.cursor()
    columns = ', '.join(CHANNEL_CSV_FIELDS)
    existing_by_unique_id = {}
    existing_by_psk = {}
    for row in c.execute(f"SELECT {columns} FROM channels").fetchall():
        record = _channel_row_to_dict(row)
        existing_by_unique_id[record['unique_id']] = record
        existing_by_psk[record['psk']] = record

    if replace:
        c.execute("DELETE FROM channels")
        conn.commit()
        existing_by_unique_id = {}
        existing_by_psk = {}

    inserted = 0
    updated = 0
    unchanged = 0
    reset_sync_keys = []

    for parsed in parsed_rows:
        match_key = _resolve_channel_import_match(
            parsed, existing_by_unique_id, existing_by_psk,
        )
        if match_key is None:
            try:
                unique_id = _insert_channel_row(c, parsed)
            except sqlite3.IntegrityError:
                errors.append(
                    f"Could not insert channel '{parsed['name']}': unique_id or psk already exists."
                )
                continue
            record = dict(parsed)
            if not record['unique_id']:
                record['unique_id'] = unique_id
            record['synced'] = _channel_synced_value_for_import(record)
            existing_by_unique_id[record['unique_id']] = record
            existing_by_psk[record['psk']] = record
            inserted += 1
            if record['publish'] == 'Y':
                reset_sync_keys.append(record['unique_id'])
            continue

        existing = existing_by_unique_id[match_key]
        if not _channel_row_differs(existing, parsed):
            unchanged += 1
            continue
        try:
            unique_id = _update_channel_row(c, parsed, existing)
        except sqlite3.IntegrityError:
            errors.append(
                f"Could not update channel '{parsed['name']}': unique_id or psk conflicts with another row."
            )
            continue
        updated_record = dict(parsed)
        if not updated_record['unique_id']:
            updated_record['unique_id'] = unique_id
        updated_record['synced'] = _channel_synced_value_for_import(updated_record, changed=True)
        old_psk = existing['psk']
        existing_by_unique_id[unique_id] = updated_record
        existing_by_psk[updated_record['psk']] = updated_record
        if old_psk != updated_record['psk'] and old_psk in existing_by_psk:
            del existing_by_psk[old_psk]
        updated += 1
        if updated_record['publish'] == 'Y':
            reset_sync_keys.append(unique_id)

    conn.commit()

    for unique_id in reset_sync_keys:
        reset_outbound_sync('channels', unique_id, 'unique_id', unique_id)

    return {
        'inserted': inserted,
        'updated': updated,
        'unchanged': unchanged,
        'errors': errors,
    }


def get_channels():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, psk FROM channels WHERE publish = 'Y' AND deleted = 'N'")
    return c.fetchall()


def _queue_pending_sync_delete(record_type, record_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO pending_sync_deletes (record_type, record_key, created) "
        "VALUES (?, ?, ?)",
        (record_type, record_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()


def sync_pending_deletes(sync_peers, interface):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT record_type, record_key FROM pending_sync_deletes ORDER BY created, record_key"
    )
    pending_rows = c.fetchall()
    if not pending_rows:
        return

    mail_peers = filter_peers_for_record_type(sync_peers, 'mail')

    for record_type, record_key in pending_rows:
        if record_type != 'mail':
            continue
        if not mail_peers:
            c.execute(
                "DELETE FROM pending_sync_deletes WHERE record_type = ? AND record_key = ?",
                (record_type, record_key),
            )
            conn.commit()
            continue
        if send_delete_mail_to_bbs_nodes(record_key, mail_peers, interface):
            c.execute(
                "DELETE FROM pending_sync_deletes WHERE record_type = ? AND record_key = ?",
                (record_type, record_key),
            )
            conn.commit()
            logging.info(f"Synced pending mail delete for {record_key} to all peers.")
        else:
            logging.warning(
                f"Pending mail delete for {record_key} sync incomplete; will retry pending peers."
            )


def delete_mail_by_admin(mail_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT unique_id FROM mail WHERE id = ?", (mail_id,))
    row = c.fetchone()
    if row is None:
        return False
    unique_id = row[0]
    c.execute("DELETE FROM mail WHERE id = ?", (mail_id,))
    deleted = c.rowcount
    conn.commit()
    if deleted > 0:
        c.execute(
            "DELETE FROM record_sync_peers WHERE record_type = ? AND record_key = ?",
            ('mail', unique_id),
        )
        conn.commit()
        _queue_pending_sync_delete('mail', unique_id)
        return True
    return False


def delete_mail_from_sync(unique_id, bbs_nodes=None, interface=None):
    """Delete mail received via DELETE_MAIL sync without mailbox authorization."""
    unique_id = (unique_id or "").strip()
    if not unique_id:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM mail WHERE unique_id = ?", (unique_id,))
    deleted = c.rowcount > 0
    conn.commit()
    if not deleted:
        logging.info(f"No mail found for sync delete unique_id: {unique_id}")
        return False

    c.execute(
        "DELETE FROM record_sync_peers WHERE record_type = ? AND record_key = ?",
        ('mail', unique_id),
    )
    conn.commit()

    sync_peers = get_sync_peers_from_interface(interface, bbs_nodes or [])
    mail_peers = filter_peers_for_record_type(sync_peers, 'mail')
    if mail_peers and interface:
        send_delete_mail_to_bbs_nodes(unique_id, mail_peers, interface)
    logging.info(f"Mail with unique_id: {unique_id} deleted via sync.")
    return True


def _mark_channel_for_reconcile(channel_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE channels SET deleted = 'Y', delete_reconcile = 'Y' "
        "WHERE id = ? AND deleted = 'N'",
        (channel_id,),
    )
    conn.commit()
    return c.rowcount > 0


def mark_channel_for_reconcile_by_sync(unique_id, sender_node_id=None):
    unique_id = (unique_id or '').strip()
    if not unique_id:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM channels WHERE unique_id = ? AND deleted = 'N'",
        (unique_id,),
    )
    row = c.fetchone()
    if row is None:
        return False

    channel_id = row[0]
    marked = _mark_channel_for_reconcile(channel_id)
    if marked:
        logging.info(
            f"Marked channel {channel_id} for reconcile after DELETE_CHANNEL sync "
            f"from peer {sender_node_id} (unique_id: {unique_id})."
        )
    return marked


def get_reconcile_channels():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, name, psk, publish, unique_id FROM channels "
        "WHERE delete_reconcile = 'Y' ORDER BY id"
    )
    return c.fetchall()


def restore_reconcile_channel(channel_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE channels SET deleted = 'N', delete_reconcile = 'N' "
        "WHERE id = ? AND delete_reconcile = 'Y'",
        (channel_id,),
    )
    conn.commit()
    return c.rowcount > 0


def confirm_reconcile_channel_delete(channel_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT unique_id FROM channels WHERE id = ? AND delete_reconcile = 'Y'", (channel_id,))
    row = c.fetchone()
    if row is None:
        return False
    unique_id = row[0]
    c.execute("DELETE FROM channels WHERE id = ? AND delete_reconcile = 'Y'", (channel_id,))
    conn.commit()
    if c.rowcount > 0:
        c.execute(
            "DELETE FROM record_sync_peers WHERE record_type = ? AND record_key = ?",
            ('channels', unique_id),
        )
        conn.commit()
    return c.rowcount > 0


def mark_channel_deleted(channel_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT unique_id FROM channels WHERE id = ? AND deleted = 'N'", (channel_id,))
    row = c.fetchone()
    if row is None:
        return False
    unique_id = row[0]
    c.execute(
        "UPDATE channels SET deleted = 'Y', synced = 'N' WHERE id = ? AND deleted = 'N'",
        (channel_id,),
    )
    conn.commit()
    if c.rowcount > 0:
        _reset_record_peer_sync('channels', unique_id)
    return c.rowcount > 0


def purge_deleted_channels(bbs_nodes, interface):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, unique_id FROM channels WHERE deleted = 'Y' AND delete_reconcile = 'N'"
    )
    deleted_channels = c.fetchall()
    sync_peers = get_sync_peers_from_interface(interface, bbs_nodes)

    for channel_id, unique_id in deleted_channels:
        c.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        conn.commit()
        if sync_peers and interface and unique_id:
            channel_peers = filter_peers_for_record_type(sync_peers, 'channels')
            if channel_peers:
                send_delete_channel_to_sync_peers(unique_id, channel_peers, interface)
            c.execute(
                "DELETE FROM record_sync_peers WHERE record_type = ? AND record_key = ?",
                ('channels', unique_id),
            )
            conn.commit()
            logging.info(
                f"Purged channel {channel_id} and sent delete sync to peer BBS nodes."
            )


def _resolve_catalog_node_hex(node_ref):
    ref = (node_ref or '').strip()
    if not ref:
        return None

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT node_hex_username FROM node_catalog "
        "WHERE node_hex_username = ? COLLATE NOCASE OR short_name = ? COLLATE NOCASE",
        (ref, ref)
    )
    row = c.fetchone()
    if row:
        return row[0]
    if ref.startswith('!'):
        return ref
    return None


def _lookup_catalog_mail_forward(recipient_id):
    recipient = str(recipient_id).strip()
    if not recipient:
        return None

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT short_name, node_hex_username, bbs_mail_forward_to FROM node_catalog "
        "WHERE node_hex_username = ? COLLATE NOCASE OR short_name = ? COLLATE NOCASE",
        (recipient, recipient)
    )
    return c.fetchone()


def apply_mail_forwarding(recipient_id, content, interface=None):
    catalog_entry = _lookup_catalog_mail_forward(recipient_id)
    if not catalog_entry:
        return recipient_id, content

    short_name, node_hex_username, forward_to = catalog_entry
    if not forward_to or not forward_to.strip():
        return recipient_id, content

    forward_target = _resolve_catalog_node_hex(forward_to)
    if not forward_target and interface is not None:
        from .node_resolution import resolve_hex_node_id
        forward_target = resolve_hex_node_id(forward_to, interface)
    if not forward_target:
        logging.warning(
            f"Mail forward target '{forward_to}' for recipient '{recipient_id}' could not be resolved; delivering to original recipient."
        )
        return recipient_id, content

    original_node = short_name or node_hex_username
    if forward_target.lower() == node_hex_username.lower():
        logging.warning(f"Mail forward for '{original_node}' points to the same node; delivering without forwarding.")
        return recipient_id, content

    forward_note = f"\nSent to {original_node}"
    if not content.endswith(forward_note):
        content = content.rstrip() + forward_note

    logging.info(f"Forwarding mail for '{original_node}' ({node_hex_username}) to {forward_target}.")
    return forward_target, content



def add_bulletin(board, sender_short_name, subject, content, bbs_nodes, interface, unique_id=None, from_sync=False, defer_sync=False):
    conn = get_db_connection()
    c = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not unique_id:
        unique_id = str(uuid.uuid4())

    c.execute("SELECT 1 FROM bulletins WHERE unique_id = ?", (unique_id,))
    if c.fetchone():
        logging.info(f"Bulletin with unique_id {unique_id} already exists; skipping duplicate ingest.")
        return unique_id

    synced = 'Y' if from_sync else 'N'
    c.execute(
        "INSERT INTO bulletins (board, sender_short_name, date, subject, content, unique_id, synced) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (board, sender_short_name, date, subject, content, unique_id, synced))
    conn.commit()

    if from_sync:
        _mark_inbound_sync_complete('bulletins', unique_id)
        return unique_id

    from .urgent_alerts import maybe_send_urgent_alert_local

    maybe_send_urgent_alert_local(board, sender_short_name, subject, interface)

    if not defer_sync:
        sync_bulletin_record(unique_id, bbs_nodes, interface)

    return unique_id


def sync_bulletin_record(unique_id, bbs_nodes, interface):
    if interface is None:
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT board, sender_short_name, subject, content FROM bulletins WHERE unique_id = ?",
        (unique_id,),
    )
    row = c.fetchone()
    if row is None:
        return

    board, sender_short_name, subject, content = row

    def _send(pending_peers):
        return send_bulletin_to_sync_peers(
            board, sender_short_name, subject, content, unique_id, pending_peers, interface
        )

    _complete_local_sync('bulletins', 'unique_id', unique_id, unique_id, bbs_nodes, interface, _send)


def get_bulletins(board):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, subject, sender_short_name, date FROM bulletins "
        "WHERE board = ? COLLATE NOCASE AND deleted = 'N' "
        "ORDER BY pinned DESC, id DESC",
        (board,)
    )
    return c.fetchall()


def get_mesh_bulletins(board):
    cutoff = _bulletin_mesh_cutoff_date()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, subject, sender_short_name, date FROM bulletins "
        "WHERE board = ? COLLATE NOCASE AND deleted = 'N' "
        "AND (pinned = 'Y' OR date >= ?) "
        "ORDER BY pinned DESC, id DESC",
        (board, cutoff),
    )
    return c.fetchall()


def get_bulletin_content(bulletin_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT sender_short_name, date, subject, content FROM bulletins "
        "WHERE id = ? AND deleted = 'N'",
        (bulletin_id,)
    )
    return c.fetchone()


def get_mesh_bulletin_content(bulletin_id, board):
    cutoff = _bulletin_mesh_cutoff_date()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT sender_short_name, date, subject, content FROM bulletins "
        "WHERE id = ? AND board = ? COLLATE NOCASE AND deleted = 'N' "
        "AND (pinned = 'Y' OR date >= ?)",
        (bulletin_id, board, cutoff),
    )
    return c.fetchone()


def get_sync_protocol_for_peer(bbs_node):
    bbs_node = (bbs_node or '').strip()
    if not bbs_node:
        return None

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT sync_protocol FROM sync_peers WHERE bbs_node = ?", (bbs_node,))
    row = c.fetchone()
    if row:
        return _normalize_sync_protocol(row[0])
    return None


def count_rs_version_alerts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sync_peers WHERE rs_version_alert = 'Y'")
    return c.fetchone()[0]


def note_rs_wire_version(bbs_node, wire_version):
    """Record RS wire version from a peer; alert on config mismatch, clear on match."""
    from .sync_wire import rs_wire_version_for_protocol

    bbs_node = (bbs_node or '').strip()
    if not bbs_node:
        return False

    try:
        wire_version = int(wire_version)
    except (TypeError, ValueError):
        return False

    configured = get_sync_protocol_for_peer(bbs_node)
    expected = rs_wire_version_for_protocol(configured)
    if expected is None:
        return False

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT rs_version_alert FROM sync_peers WHERE bbs_node = ?",
        (bbs_node,),
    )
    row = c.fetchone()
    if not row:
        return False

    if wire_version == expected:
        if (row[0] or 'N') == 'Y':
            c.execute(
                "UPDATE sync_peers SET rs_version_alert = 'N', rs_wire_version_seen = ? "
                "WHERE bbs_node = ?",
                (wire_version, bbs_node),
            )
            conn.commit()
        return False

    was_alert = (row[0] or 'N') == 'Y'
    c.execute(
        "UPDATE sync_peers SET rs_version_alert = 'Y', rs_wire_version_seen = ? "
        "WHERE bbs_node = ?",
        (wire_version, bbs_node),
    )
    conn.commit()
    if not was_alert:
        logging.warning(
            "RS wire version mismatch for peer %s: configured %s (v%d), received v%d",
            bbs_node,
            configured,
            expected,
            wire_version,
        )
    return True


def clear_rs_version_alert(bbs_node):
    bbs_node = (bbs_node or '').strip()
    if not bbs_node:
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE sync_peers SET rs_version_alert = 'N', rs_wire_version_seen = NULL "
        "WHERE bbs_node = ?",
        (bbs_node,),
    )
    conn.commit()


def _mark_bulletin_for_reconcile(bulletin_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE bulletins SET deleted = 'Y', delete_reconcile = 'Y' "
        "WHERE id = ? AND deleted = 'N'",
        (bulletin_id,)
    )
    conn.commit()
    return c.rowcount > 0


def get_reconcile_bulletins():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, board, sender_short_name, date, subject, unique_id FROM bulletins "
        "WHERE delete_reconcile = 'Y' ORDER BY id"
    )
    return c.fetchall()


def restore_reconcile_bulletin(bulletin_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE bulletins SET deleted = 'N', delete_reconcile = 'N' "
        "WHERE id = ? AND delete_reconcile = 'Y'",
        (bulletin_id,)
    )
    conn.commit()
    return c.rowcount > 0


def confirm_reconcile_bulletin_delete(bulletin_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT unique_id FROM bulletins WHERE id = ? AND delete_reconcile = 'Y'",
        (bulletin_id,),
    )
    row = c.fetchone()
    unique_id = row[0] if row else None
    c.execute(
        "DELETE FROM bulletins WHERE id = ? AND delete_reconcile = 'Y'",
        (bulletin_id,),
    )
    conn.commit()
    if c.rowcount > 0 and unique_id:
        from .urgent_alerts import clear_pending_urgent_alert

        clear_pending_urgent_alert(unique_id)
    return c.rowcount > 0


def mark_bulletin_deleted(bulletin_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT unique_id FROM bulletins WHERE id = ? AND deleted = 'N'", (bulletin_id,))
    row = c.fetchone()
    if row is None:
        return False
    unique_id = row[0]
    c.execute(
        "UPDATE bulletins SET deleted = 'Y', synced = 'N' WHERE id = ? AND deleted = 'N'",
        (bulletin_id,)
    )
    conn.commit()
    if c.rowcount > 0:
        _reset_record_peer_sync('bulletins', unique_id)
        from .urgent_alerts import clear_pending_urgent_alert

        clear_pending_urgent_alert(unique_id)
    return c.rowcount > 0


def delete_bulletin(bulletin_id, bbs_nodes, interface):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT unique_id FROM bulletins WHERE id = ?", (bulletin_id,))
    row = c.fetchone()
    if row is None:
        return
    unique_id = row[0]
    c.execute("DELETE FROM bulletins WHERE id = ?", (bulletin_id,))
    conn.commit()
    from .urgent_alerts import clear_pending_urgent_alert

    clear_pending_urgent_alert(unique_id)
    sync_peers = get_sync_peers_from_interface(interface, bbs_nodes)
    bulletin_peers = filter_peers_for_record_type(sync_peers, 'bulletins')
    if bulletin_peers and interface:
        send_delete_bulletin_to_sync_peers(bulletin_id, unique_id, bulletin_peers, interface)


def delete_bulletin_by_sync_identifier(identifier, sender_node_id=None):
    identifier = (identifier or '').strip()
    if not identifier:
        return False

    protocol = get_sync_protocol_for_peer(sender_node_id) or 'tc2'
    conn = get_db_connection()
    c = conn.cursor()

    from .sync_wire import is_rs_sync_protocol

    if is_rs_sync_protocol(protocol) and _is_uuid(identifier):
        c.execute("DELETE FROM bulletins WHERE unique_id = ?", (identifier,))
        conn.commit()
        return c.rowcount > 0

    bulletin_id = None
    if _is_uuid(identifier):
        c.execute("SELECT id FROM bulletins WHERE unique_id = ?", (identifier,))
        row = c.fetchone()
        if row is None:
            return False
        bulletin_id = row[0]
    else:
        try:
            bulletin_id = int(identifier)
        except ValueError:
            return False
        c.execute("SELECT id FROM bulletins WHERE id = ?", (bulletin_id,))
        if c.fetchone() is None:
            return False

    marked = _mark_bulletin_for_reconcile(bulletin_id)
    if marked:
        logging.info(
            f"Marked bulletin {bulletin_id} for reconcile after tc2 delete sync "
            f"from peer {sender_node_id} (identifier: {identifier})."
        )
    return marked


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def is_sync_uuid(value):
    return _is_uuid(value)


def purge_deleted_bulletins(bbs_nodes, interface):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, unique_id FROM bulletins WHERE deleted = 'Y' AND delete_reconcile = 'N'")
    deleted_bulletins = c.fetchall()
    sync_peers = get_sync_peers_from_interface(interface, bbs_nodes)

    for bulletin_id, unique_id in deleted_bulletins:
        c.execute("DELETE FROM bulletins WHERE id = ?", (bulletin_id,))
        conn.commit()
        if sync_peers and interface:
            bulletin_peers = filter_peers_for_record_type(sync_peers, 'bulletins')
            if bulletin_peers:
                send_delete_bulletin_to_sync_peers(bulletin_id, unique_id, bulletin_peers, interface)
            logging.info(f"Purged bulletin {bulletin_id} and sent delete sync to peer BBS nodes.")

def add_mail(
    sender_id,
    sender_short_name,
    recipient_id,
    subject,
    content,
    bbs_nodes,
    interface,
    unique_id=None,
    from_sync=False,
    defer_sync=False,
    recipient_short_name=None,
):
    from .node_resolution import (
        is_hex_node_id,
        normalize_recipient_fields,
        normalize_sender_fields,
    )

    sender_id, sender_short_name = normalize_sender_fields(
        sender_id, sender_short_name, interface,
    )
    recipient_hex, recipient_short_name = normalize_recipient_fields(
        recipient_id, recipient_short_name, interface,
    )
    recipient_id, content = apply_mail_forwarding(
        recipient_hex or recipient_short_name, content, interface,
    )
    if is_hex_node_id(recipient_id):
        recipient_hex = recipient_id
    elif recipient_short_name:
        resolved_hex, _ = normalize_recipient_fields(recipient_short_name, recipient_short_name, interface)
        recipient_hex = resolved_hex
    else:
        recipient_hex = None

    conn = get_db_connection()
    c = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not unique_id:
        unique_id = str(uuid.uuid4())

    if from_sync:
        c.execute("SELECT 1 FROM mail WHERE unique_id = ?", (unique_id,))
        if c.fetchone():
            logging.info(f"Mail with unique_id {unique_id} already exists; skipping duplicate ingest.")
            return unique_id, recipient_hex or recipient_short_name

    synced = 'Y' if from_sync else 'N'
    c.execute(
        "INSERT INTO mail (sender, sender_short_name, recipient, recipient_short_name, date, subject, content, unique_id, synced) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sender_id, sender_short_name, recipient_hex, recipient_short_name,
            date, subject, content, unique_id, synced,
        ),
    )
    conn.commit()

    if from_sync:
        _mark_inbound_sync_complete('mail', unique_id)
        return unique_id, recipient_hex or recipient_short_name

    if not defer_sync:
        sync_mail_record(unique_id, bbs_nodes, interface)
    return unique_id, recipient_hex or recipient_short_name


def sync_mail_record(unique_id, bbs_nodes, interface):
    if interface is None:
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT sender, sender_short_name, recipient, recipient_short_name, subject, content FROM mail WHERE unique_id = ?",
        (unique_id,),
    )
    row = c.fetchone()
    if row is None:
        return

    sender_id, sender_short_name, recipient_id, recipient_short_name, subject, content = row

    def _send(pending_peers):
        return send_mail_to_bbs_nodes(
            sender_id, sender_short_name, recipient_id, recipient_short_name,
            subject, content, unique_id, pending_peers, interface,
        )

    _complete_local_sync('mail', 'unique_id', unique_id, unique_id, bbs_nodes, interface, _send)

def get_mail(recipient_id, interface=None):
    from .node_resolution import recipient_mailbox_keys

    mailbox_keys = recipient_mailbox_keys(recipient_id, interface)
    if not mailbox_keys:
        return []

    conn = get_db_connection()
    c = conn.cursor()
    placeholders = ", ".join("?" for _ in mailbox_keys)
    c.execute(
        f"SELECT id, sender_short_name, subject, date, unique_id, read FROM mail "
        f"WHERE recipient IN ({placeholders}) "
        f"OR recipient_short_name IN ({placeholders}) "
        f"ORDER BY id",
        mailbox_keys + mailbox_keys,
    )
    return c.fetchall()


def get_mail_content(mail_id, recipient_id, interface=None):
    from .node_resolution import recipient_mailbox_keys

    mailbox_keys = recipient_mailbox_keys(recipient_id, interface)
    if not mailbox_keys:
        return None

    conn = get_db_connection()
    c = conn.cursor()
    placeholders = ", ".join("?" for _ in mailbox_keys)
    c.execute(
        f"SELECT sender_short_name, date, subject, content, unique_id FROM mail "
        f"WHERE id = ? AND (recipient IN ({placeholders}) OR recipient_short_name IN ({placeholders}))",
        (mail_id,) + tuple(mailbox_keys) + tuple(mailbox_keys),
    )
    row = c.fetchone()
    if row is not None:
        c.execute(
            f"UPDATE mail SET read = 'Y' WHERE id = ? AND "
            f"(recipient IN ({placeholders}) OR recipient_short_name IN ({placeholders}))",
            (mail_id,) + tuple(mailbox_keys) + tuple(mailbox_keys),
        )
        conn.commit()
    return row

def delete_mail(unique_id, recipient_id, bbs_nodes, interface):
    from .node_resolution import recipient_mailbox_keys

    mailbox_keys = recipient_mailbox_keys(recipient_id, interface)
    if not mailbox_keys:
        logging.error(f"Mail delete denied for unique_id {unique_id}; recipient unknown.")
        return

    conn = get_db_connection()
    c = conn.cursor()
    try:
        placeholders = ", ".join("?" for _ in mailbox_keys)
        c.execute(
            f"DELETE FROM mail WHERE unique_id = ? "
            f"AND (recipient IN ({placeholders}) OR recipient_short_name IN ({placeholders}))",
            (unique_id,) + tuple(mailbox_keys) + tuple(mailbox_keys),
        )
        if c.rowcount <= 0:
            logging.error(
                f"Mail delete denied for unique_id {unique_id}; message not found for recipient.",
            )
            conn.commit()
            return

        conn.commit()
        c.execute(
            "DELETE FROM record_sync_peers WHERE record_type = ? AND record_key = ?",
            ('mail', unique_id),
        )
        conn.commit()
        logging.info(f"Attempting to delete mail with unique_id: {unique_id} by {recipient_id}")
        sync_peers = get_sync_peers_from_interface(interface, bbs_nodes)
        mail_peers = filter_peers_for_record_type(sync_peers, 'mail')
        if mail_peers:
            send_delete_mail_to_bbs_nodes(unique_id, mail_peers, interface)
        logging.info(f"Mail with unique_id: {unique_id} deleted and sync message sent.")
    except Exception as e:
        logging.error(f"Error deleting mail with unique_id {unique_id}: {e}")
        raise


def get_sender_id_by_mail_id(mail_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT sender FROM mail WHERE id = ?", (mail_id,))
    result = c.fetchone()
    if result:
        return result[0]
    return None
