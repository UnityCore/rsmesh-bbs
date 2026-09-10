import configparser
import logging
import shutil
import sqlite3
import time
import uuid
from pathlib import Path

import yaml

from .config_init import DEFAULT_CONFIG_FILE
from .version import BBS_DB_FILE

TC2_DB_FILE = "bulletins.db"
TC2_INI_FILE = "config.ini"


def prepare_tc2_upgrade(config_file=None):
    """Import TC2 config.ini and bulletins.db before RSMesh-BBS startup."""
    config_file = config_file or DEFAULT_CONFIG_FILE
    migrated_ini = migrate_tc2_ini_to_yaml(config_file)
    migrated_db = import_tc2_database_file()
    if migrated_ini:
        print(f"Migrated {TC2_INI_FILE} to {config_file}.")
    if migrated_db:
        print(f"Imported {TC2_DB_FILE} as {BBS_DB_FILE}.")
    return migrated_ini or migrated_db


def migrate_tc2_ini_to_yaml(config_file=None):
    config_file = config_file or DEFAULT_CONFIG_FILE
    yaml_path = Path(config_file)
    ini_path = Path(TC2_INI_FILE)
    if yaml_path.exists() or not ini_path.exists():
        return False

    parser = configparser.ConfigParser()
    parser.read(ini_path, encoding="utf-8")

    config = {"bbs": {"board_name": "RSMesh BBS"}}

    if parser.has_section("interface"):
        interface = {"type": parser.get("interface", "type", fallback="serial")}
        port = parser.get("interface", "port", fallback="").strip()
        hostname = parser.get("interface", "hostname", fallback="").strip()
        if port:
            interface["port"] = port
        if hostname:
            interface["hostname"] = hostname
        config["interface"] = interface

    if parser.has_section("allow_list"):
        allowed = parser.get("allow_list", "allowed_nodes", fallback="").strip()
        nodes = [node.strip() for node in allowed.split(",") if node.strip()]
        if nodes:
            config["bbs"]["superuser_node"] = nodes[0]

    with yaml_path.open("w", encoding="utf-8") as handle:
        yaml.dump(config, handle, default_flow_style=False, sort_keys=False)
    return True


def import_tc2_database_file():
    tc2_path = Path(TC2_DB_FILE)
    bbs_path = Path(BBS_DB_FILE)
    if not tc2_path.exists() or bbs_path.exists():
        return False
    shutil.copy2(tc2_path, bbs_path)
    return True


def import_tc2_sync_peers_from_ini(ini_path=None):
    ini_path = Path(ini_path or TC2_INI_FILE)
    if not ini_path.exists():
        return 0

    from .db_operations import get_db_connection

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sync_peers")
    if c.fetchone()[0] > 0:
        return 0

    parser = configparser.ConfigParser()
    parser.read(ini_path, encoding="utf-8")
    if not parser.has_section("sync"):
        return 0

    bbs_nodes_raw = parser.get("sync", "bbs_nodes", fallback="").strip()
    if not bbs_nodes_raw:
        return 0

    migrated = 0
    now = int(time.time())
    for node in bbs_nodes_raw.split(","):
        node = node.strip()
        if not node:
            continue
        c.execute(
            "INSERT OR IGNORE INTO sync_peers "
            "(bbs_node, bbs_name, sync_protocol, last_heard, sync_bulletins, sync_mail, sync_channels, "
            "sync_mesh_nodes, ingest_bulletins, ingest_channels) "
            "VALUES (?, NULL, 'tc2', ?, 'N', 'N', 'N', 'N', 'N', 'N')",
            (node, now),
        )
        migrated += c.rowcount

    import_tc2_allow_list_to_sysadmin(c, ini_path)
    conn.commit()
    if migrated:
        print(
            f"Migrated {migrated} sync peer(s) from {TC2_INI_FILE} with all sync flags disabled. "
            "Use rsmesh-bbs_admin.py to edit each peer and enable sync before records will sync."
        )
    return migrated


def import_tc2_allow_list_to_sysadmin(c, ini_path):
    parser = configparser.ConfigParser()
    parser.read(ini_path, encoding="utf-8")
    if not parser.has_section("allow_list"):
        return

    allowed = parser.get("allow_list", "allowed_nodes", fallback="").strip()
    for node in allowed.split(","):
        node = node.strip()
        if not node:
            continue
        short_name = node[-4:] if len(node) >= 4 else node
        c.execute(
            "INSERT OR IGNORE INTO sysadmin_nodes (short_name, node_hex_username) VALUES (?, ?)",
            (short_name, node),
        )


def needs_tc2_database_migration(c):
    if not _table_exists(c, "bulletins"):
        return False
    bulletin_columns = _table_columns(c, "bulletins")
    if "synced" not in bulletin_columns:
        return True
    if _table_exists(c, "channels") and "url" in _table_columns(c, "channels"):
        return True
    return False


def migrate_tc2_database(c):
    if not _table_exists(c, "bulletins"):
        return False

    migrated = False
    if needs_tc2_database_migration(c):
        logging.info("Migrating stock TC2 database schema to RSMesh-BBS.")
        if _table_exists(c, "channels") and "url" in _table_columns(c, "channels"):
            _migrate_tc2_channels_url_to_psk(c)
        _create_rsmesh_tables(c)
        migrated = True

    ensure_tc2_upgrade_schema(c)
    return migrated


def ensure_tc2_upgrade_schema(c):
    """Idempotent schema completion for TC2 imports and interrupted upgrades."""
    if not _table_exists(c, "bulletins"):
        return

    _upgrade_bulletins_schema(c)
    _upgrade_mail_schema(c)
    _upgrade_channels_schema(c)
    _upgrade_sync_peers_schema(c)
    _create_rsmesh_support_tables(c)


def _upgrade_bulletins_schema(c):
    _add_column_if_missing(c, "bulletins", "deleted", "TEXT NOT NULL DEFAULT 'N'")
    _add_column_if_missing(c, "bulletins", "delete_reconcile", "TEXT NOT NULL DEFAULT 'N'")
    _add_column_if_missing(c, "bulletins", "synced", "TEXT NOT NULL DEFAULT 'Y'")
    _add_column_if_missing(c, "bulletins", "pinned", "TEXT NOT NULL DEFAULT 'N'")


def _upgrade_mail_schema(c):
    if not _table_exists(c, "mail"):
        return

    _add_column_if_missing(c, "mail", "synced", "TEXT NOT NULL DEFAULT 'Y'")
    _add_column_if_missing(c, "mail", "read", "TEXT NOT NULL DEFAULT 'N'")
    _add_column_if_missing(c, "mail", "recipient_short_name", "TEXT")
    _migrate_mail_recipient_nullable(c)
    _backfill_mail_recipient_short_names(c)


def _upgrade_channels_schema(c):
    if not _table_exists(c, "channels"):
        return

    _add_column_if_missing(c, "channels", "publish", "TEXT NOT NULL DEFAULT 'Y'")
    _add_column_if_missing(c, "channels", "synced", "TEXT NOT NULL DEFAULT 'Y'")
    _add_column_if_missing(c, "channels", "unique_id", "TEXT")
    _add_column_if_missing(c, "channels", "deleted", "TEXT NOT NULL DEFAULT 'N'")
    _add_column_if_missing(c, "channels", "delete_reconcile", "TEXT NOT NULL DEFAULT 'N'")


def _upgrade_sync_peers_schema(c):
    if not _table_exists(c, "sync_peers"):
        return

    _add_column_if_missing(c, "sync_peers", "sync_mesh_nodes", "TEXT NOT NULL DEFAULT 'N'")
    _add_column_if_missing(c, "sync_peers", "ingest_bulletins", "TEXT NOT NULL DEFAULT 'Y'")
    _add_column_if_missing(c, "sync_peers", "ingest_channels", "TEXT NOT NULL DEFAULT 'Y'")
    _add_column_if_missing(c, "sync_peers", "rs_version_alert", "TEXT NOT NULL DEFAULT 'N'")
    _add_column_if_missing(c, "sync_peers", "rs_wire_version_seen", "INTEGER")
    _add_column_if_missing(c, "sync_peers", "enabled", "TEXT NOT NULL DEFAULT 'Y'")
    c.execute(
        "UPDATE sync_peers SET sync_mesh_nodes = 'N' WHERE sync_protocol = 'tc2'"
    )


def _create_rsmesh_support_tables(c):
    c.execute(
        """CREATE TABLE IF NOT EXISTS mesh_nodes (
               node_id TEXT PRIMARY KEY,
               short_name TEXT,
               long_name TEXT,
               last_heard INTEGER,
               last_updated INTEGER NOT NULL
           )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS pending_sync_deletes (
               record_type TEXT NOT NULL,
               record_key TEXT NOT NULL,
               created TEXT NOT NULL,
               PRIMARY KEY (record_type, record_key)
           )"""
    )


def _mail_recipient_is_nullable(c):
    for _cid, name, _type, notnull, _dflt, _pk in c.execute("PRAGMA table_info(mail)").fetchall():
        if name == "recipient":
            return notnull == 0
    return False


def _migrate_mail_recipient_nullable(c):
    if _mail_recipient_is_nullable(c):
        return

    c.execute(
        """CREATE TABLE mail_rsmesh (
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
           )"""
    )
    c.execute(
        """INSERT INTO mail_rsmesh (
               id, sender, sender_short_name, recipient, recipient_short_name,
               date, subject, content, unique_id, synced, read
           )
           SELECT
               id, sender, sender_short_name, recipient, recipient_short_name,
               date, subject, content, unique_id, synced, read
           FROM mail"""
    )
    c.execute("DROP TABLE mail")
    c.execute("ALTER TABLE mail_rsmesh RENAME TO mail")


def _backfill_mail_recipient_short_names(c):
    from .node_resolution import is_hex_node_id

    rows = c.execute(
        "SELECT id, recipient FROM mail WHERE recipient_short_name IS NULL OR recipient_short_name = ''"
    ).fetchall()
    for mail_id, recipient in rows:
        recipient = (recipient or "").strip()
        if not recipient:
            continue
        if is_hex_node_id(recipient):
            continue
        c.execute(
            "UPDATE mail SET recipient_short_name = ?, recipient = NULL WHERE id = ?",
            (recipient, mail_id),
        )


def _table_exists(c, table_name):
    row = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(c, table_name):
    return [row[1] for row in c.execute(f"PRAGMA table_info({table_name})")]


def _add_column_if_missing(c, table_name, column_name, definition):
    if column_name not in _table_columns(c, table_name):
        c.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _migrate_tc2_channels_url_to_psk(c):
    c.execute(
        """CREATE TABLE channels_rsmesh (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT NOT NULL,
               psk TEXT NOT NULL,
               publish TEXT NOT NULL DEFAULT 'Y',
               synced TEXT NOT NULL DEFAULT 'Y',
               unique_id TEXT,
               deleted TEXT NOT NULL DEFAULT 'N',
               delete_reconcile TEXT NOT NULL DEFAULT 'N'
           )"""
    )
    rows = c.execute("SELECT id, name, url FROM channels").fetchall()
    for channel_id, name, url in rows:
        c.execute(
            "INSERT INTO channels_rsmesh (id, name, psk, publish, synced, unique_id) "
            "VALUES (?, ?, ?, 'Y', 'Y', ?)",
            (channel_id, name, url, str(uuid.uuid4())),
        )
    c.execute("DROP TABLE channels")
    c.execute("ALTER TABLE channels_rsmesh RENAME TO channels")


def _create_rsmesh_tables(c):
    c.execute(
        """CREATE TABLE IF NOT EXISTS sync_peers (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               bbs_node TEXT NOT NULL UNIQUE,
               bbs_name TEXT,
               sync_protocol TEXT NOT NULL DEFAULT 'tc2',
               last_heard INTEGER,
               sync_bulletins TEXT NOT NULL DEFAULT 'Y',
               sync_mail TEXT NOT NULL DEFAULT 'Y',
               sync_channels TEXT NOT NULL DEFAULT 'Y',
               ingest_bulletins TEXT NOT NULL DEFAULT 'Y',
               ingest_channels TEXT NOT NULL DEFAULT 'Y'
           )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS sysadmin_nodes (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               short_name TEXT NOT NULL,
               node_hex_username TEXT NOT NULL
           )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS node_catalog (
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
           )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS sys_config (
               cfg_section TEXT NOT NULL,
               cfg_key TEXT NOT NULL,
               cfg_value TEXT,
               PRIMARY KEY (cfg_section, cfg_key)
           )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS record_sync_peers (
               record_type TEXT NOT NULL,
               record_key TEXT NOT NULL,
               peer_id INTEGER NOT NULL,
               synced TEXT NOT NULL DEFAULT 'N',
               PRIMARY KEY (record_type, record_key, peer_id),
               FOREIGN KEY (peer_id) REFERENCES sync_peers(id) ON DELETE CASCADE
           )"""
    )
