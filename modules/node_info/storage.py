import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import yaml

from rsmesh_bbs.time_format import format_relative_time, format_timestamp
from rsmesh_bbs.utils import join_display_fields
from rsmesh_bbs.sqlite_config import configure_sqlite_connection

_MODULE_DIR = Path(__file__).resolve().parent
DB_PATH = None
PURGE_SECONDS = 1800


class NodeDirectory:
    def lookup_by_short_name(self, short_name):
        return get_nodes_by_short_name(short_name)

    def get_record(self, node_id):
        return get_node_record(node_id)


def configure(module_dir=None):
    global DB_PATH, PURGE_SECONDS
    module_path = Path(module_dir) if module_dir is not None else _MODULE_DIR
    config_path = module_path / "config.yml"
    if config_path.exists():
        with config_path.open(encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        try:
            PURGE_SECONDS = int(config.get("purge_minutes", 30)) * 60
        except (TypeError, ValueError):
            PURGE_SECONDS = 1800
    DB_PATH = str(module_path / "node_info.db")
    setup_node_db()


def _connect():
    if DB_PATH is None:
        configure()
    conn = sqlite3.connect(DB_PATH)
    configure_sqlite_connection(conn)
    return conn


def setup_node_db():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS node_info (
               node_id TEXT PRIMARY KEY,
               short_name TEXT,
               long_name TEXT,
               snr REAL,
               rssi REAL,
               last_heard INTEGER,
               latitude REAL,
               longitude REAL,
               hops INTEGER,
               last_updated INTEGER,
               channel_quality TEXT
           )"""
    )
    _ensure_node_info_indexes(c)
    conn.commit()
    conn.close()


def _ensure_node_info_indexes(c):
    statements = (
        "CREATE INDEX IF NOT EXISTS idx_node_info_last_updated ON node_info(last_updated)",
        "CREATE INDEX IF NOT EXISTS idx_node_info_short_name_list "
        "ON node_info(short_name COLLATE NOCASE, node_id, channel_quality, hops, last_heard)",
        "CREATE INDEX IF NOT EXISTS idx_node_info_last_heard_list "
        "ON node_info(last_heard DESC, node_id, short_name, hops, channel_quality)",
    )
    for statement in statements:
        c.execute(statement)
    c.execute("ANALYZE node_info")


def assess_channel_quality(rssi, snr):
    if rssi is not None and snr is not None:
        if rssi > -90 and snr > 5:
            return "GOOD"
        if rssi > -105 and snr > 2:
            return "FAIR"
        return "POOR"
    if snr is not None:
        if snr > 5:
            return "GOOD"
        if snr > 2:
            return "FAIR"
        return "POOR"
    if rssi is not None:
        if rssi > -90:
            return "GOOD"
        if rssi > -105:
            return "FAIR"
        return "POOR"
    return "UNKNOWN"


def _unk(value):
    return "UNK" if value is None else str(value)


def _format_hops(hops):
    if hops is None:
        return "UNK hops"
    count = int(hops)
    if count == 1:
        return "1 hop"
    return f"{count} hops"


def format_mesh_node_list_lines():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT short_name, node_id, channel_quality, hops, last_heard "
        "FROM node_info ORDER BY short_name COLLATE NOCASE"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return ["No nodes in database."]
    lines = []
    for short_name, node_id, channel_quality, hops, last_heard in rows:
        lines.append(
            join_display_fields(
                _unk(short_name),
                _unk(node_id),
                _unk(channel_quality),
                _format_hops(hops),
                format_relative_time(last_heard),
            )
        )
    return lines


def _admin_node_entry_lines(row):
    short_name, long_name, node_id, latitude, longitude, hops, snr, rssi, last_heard, last_updated, channel_quality = row
    snr_text = "UNK" if snr is None else str(snr)
    rssi_text = "UNK" if rssi is None else str(rssi)
    hops_text = _unk(hops)
    if latitude is None or str(latitude).strip() == "":
        loc_text = "Unknown"
    elif longitude is None or str(longitude).strip() == "":
        loc_text = "Unknown"
    else:
        loc_text = f"{float(latitude):.3f}, {float(longitude):.3f}"
    return [
        join_display_fields(
            f"{_unk(short_name)} - {_unk(long_name)} [{_unk(node_id)}]",
            f"Seen: {format_relative_time(last_heard)}",
        ),
        "  " + join_display_fields(
            f"Signal: {_unk(channel_quality)} (SNR {snr_text} RSSI {rssi_text})",
            f"Hops: {hops_text}",
            f"Loc: {loc_text}",
        ),
        f"  Updated: {format_timestamp(last_updated)}",
    ]


def format_admin_node_detail_lines():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT short_name, long_name, node_id, latitude, longitude, hops, snr, rssi, "
        "last_heard, last_updated, channel_quality "
        "FROM node_info ORDER BY short_name COLLATE NOCASE"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return ["No nodes in database."]
    lines = []
    for row in rows:
        lines.extend(_admin_node_entry_lines(row))
    return lines


def update_node_info(node_id, short_name, long_name, snr, rssi, last_heard, lat, lon, hops):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT short_name, long_name, snr, rssi, last_heard, latitude, longitude, hops, "
        "channel_quality, last_updated FROM node_info WHERE node_id = ?",
        (node_id,),
    )
    existing = c.fetchone()
    current_time = int(time.time())
    channel_quality = assess_channel_quality(rssi, snr)
    new_values = (short_name, long_name, snr, rssi, last_heard, lat, lon, hops, channel_quality)
    if not existing:
        c.execute(
            """INSERT INTO node_info
               (node_id, short_name, long_name, snr, rssi, last_heard, latitude, longitude, hops,
                last_updated, channel_quality)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (node_id,) + new_values + (current_time,),
        )
        logging.info("Added new node %s (Short name: %s)", node_id, short_name)
    else:
        changes = []
        if existing[0] != short_name and short_name is not None:
            changes.append(f"name: {existing[0]} → {short_name}")
        if existing[2] != snr:
            changes.append(f"SNR: {existing[2] or 'N/A'} → {snr or 'N/A'} dB")
        if existing[3] != rssi:
            changes.append(f"RSSI: {existing[3] or 'N/A'} → {rssi or 'N/A'} dBm")
        if existing[8] != channel_quality:
            changes.append(f"Quality: {existing[8] or 'UNKNOWN'} → {channel_quality}")
        if existing[7] != hops:
            changes.append(f"hops: {existing[7] or 'N/A'} → {hops or 'N/A'}")
        if changes:
            c.execute(
                """UPDATE node_info
                   SET short_name=?, long_name=?, snr=?, rssi=?, last_heard=?,
                       latitude=?, longitude=?, hops=?, channel_quality=?, last_updated=?
                   WHERE node_id=?""",
                new_values + (current_time, node_id),
            )
            logging.info("Node %s (%s): %s", node_id, short_name or node_id, ", ".join(changes))
        else:
            c.execute(
                "UPDATE node_info SET last_heard=?, last_updated=? WHERE node_id=?",
                (last_heard, current_time, node_id),
            )
    conn.commit()
    conn.close()


def get_node_record(node_id):
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM node_info WHERE node_id = ?", (node_id,))
    result = c.fetchone()
    conn.close()
    return result


def get_nodes_by_short_name(short_name):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT node_id, short_name, long_name FROM node_info WHERE short_name = ? COLLATE NOCASE",
        (short_name,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"num": node_id, "shortName": name, "longName": long_name or name}
        for node_id, name, long_name in rows
    ]


def purge_old_nodes():
    conn = _connect()
    c = conn.cursor()
    cutoff_time = int(time.time()) - PURGE_SECONDS
    c.execute("SELECT node_id, short_name FROM node_info WHERE last_updated < ?", (cutoff_time,))
    to_purge = c.fetchall()
    if to_purge:
        c.execute("DELETE FROM node_info WHERE last_updated < ?", (cutoff_time,))
        conn.commit()
        for node_id, short_name in to_purge:
            logging.info("Purged inactive node %s (Short name: %s)", node_id, short_name)
    conn.close()


def scan_mesh_nodes(interface):
    try:
        nodes = dict(interface.nodes)
        for node_id, node in nodes.items():
            try:
                if not isinstance(node_id, str):
                    continue
                node_user = node.get("user", {})
                position = node.get("position", {})
                device_metrics = node.get("deviceMetrics", {})
                snr = node.get("snr")
                rssi = node.get("rssi") or node.get("rxRssi") or device_metrics.get("rssi")
                hops_away = node.get("hopsAway", 0)
                lat = position.get("latitude")
                if lat is None and "latitudeI" in position:
                    lat = position["latitudeI"] / 1e7
                lon = position.get("longitude")
                if lon is None and "longitudeI" in position:
                    lon = position["longitudeI"] / 1e7
                update_node_info(
                    node_id=node_id,
                    short_name=node_user.get("shortName"),
                    long_name=node_user.get("longName"),
                    snr=snr,
                    rssi=rssi,
                    last_heard=node.get("lastHeard"),
                    lat=lat,
                    lon=lon,
                    hops=hops_away,
                )
            except Exception as exc:
                logging.error("Error processing node %s: %s", node_id, exc)
    except Exception as exc:
        logging.error("Error scanning mesh nodes: %s", exc)
