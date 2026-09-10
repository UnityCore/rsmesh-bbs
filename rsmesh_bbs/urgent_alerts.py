"""Urgent bulletin mesh broadcast alerts (config-gated, with admin queue)."""

import logging
from datetime import datetime

from meshtastic import BROADCAST_NUM

from .config_init import parse_config_value
from .db_operations import get_db_connection, get_sys_config_value

BBS_URGENT_ALERT_LOCAL_KEY = "send_urgent_alert_local"
BBS_URGENT_ALERT_FROM_SYNC_KEY = "send_urgent_alert_from_sync"


def _sys_config_bool(cfg_key):
    value = get_sys_config_value("bbs", cfg_key, "false")
    return parse_config_value(value) is True


def urgent_alert_local_enabled():
    return _sys_config_bool(BBS_URGENT_ALERT_LOCAL_KEY)


def urgent_alert_from_sync_enabled():
    return _sys_config_bool(BBS_URGENT_ALERT_FROM_SYNC_KEY)


def build_urgent_alert_message(sender_short_name, subject):
    return (
        f"= NEW URGENT BULLETIN =\nFrom: {sender_short_name}\n"
        f"Title: {subject}\nType HELP and select Bulletins to view."
    )


def send_urgent_mesh_alert(sender_short_name, subject, interface):
    if interface is None:
        return False
    from .utils import send_message

    message = build_urgent_alert_message(sender_short_name, subject)
    return send_message(message, BROADCAST_NUM, interface)


def maybe_send_urgent_alert_local(board, sender_short_name, subject, interface):
    if (board or "").strip().lower() != "urgent":
        return
    if not urgent_alert_local_enabled():
        return
    send_urgent_mesh_alert(sender_short_name, subject, interface)


def maybe_send_urgent_alert_from_sync(board, sender_short_name, subject, interface):
    if (board or "").strip().lower() != "urgent":
        return
    if not urgent_alert_from_sync_enabled():
        return
    send_urgent_mesh_alert(sender_short_name, subject, interface)


def enqueue_pending_urgent_alert(unique_id, sender_short_name, subject):
    unique_id = (unique_id or "").strip()
    if not unique_id:
        return False
    conn = get_db_connection()
    c = conn.cursor()
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "INSERT OR IGNORE INTO pending_urgent_alerts "
        "(unique_id, sender_short_name, subject, created) VALUES (?, ?, ?, ?)",
        (unique_id, sender_short_name, subject, created),
    )
    conn.commit()
    return c.rowcount > 0


def clear_pending_urgent_alert(unique_id):
    if not unique_id:
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM pending_urgent_alerts WHERE unique_id = ?", (unique_id,))
    conn.commit()


def _bulletin_valid_for_urgent_alert(unique_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT board, deleted FROM bulletins WHERE unique_id = ?",
        (unique_id,),
    )
    row = c.fetchone()
    if row is None:
        return False
    board, deleted = row
    if (deleted or "N").upper() == "Y":
        return False
    return (board or "").strip().lower() == "urgent"


def drain_pending_urgent_alerts(interface):
    """Process queued admin Urgent alerts on the server main loop."""
    if interface is None:
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT unique_id, sender_short_name, subject FROM pending_urgent_alerts "
        "ORDER BY created, unique_id"
    )
    rows = c.fetchall()
    if not rows:
        return

    local_enabled = urgent_alert_local_enabled()
    for unique_id, sender_short_name, subject in rows:
        if not local_enabled:
            c.execute(
                "DELETE FROM pending_urgent_alerts WHERE unique_id = ?",
                (unique_id,),
            )
            conn.commit()
            continue
        if not _bulletin_valid_for_urgent_alert(unique_id):
            c.execute(
                "DELETE FROM pending_urgent_alerts WHERE unique_id = ?",
                (unique_id,),
            )
            conn.commit()
            continue
        try:
            sent = send_urgent_mesh_alert(sender_short_name, subject, interface)
        except Exception as exc:
            logging.error(
                "Failed to send queued urgent alert for bulletin %s: %s",
                unique_id,
                exc,
                exc_info=True,
            )
            continue
        if sent:
            c.execute(
                "DELETE FROM pending_urgent_alerts WHERE unique_id = ?",
                (unique_id,),
            )
            conn.commit()
