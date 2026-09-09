"""Resolve mesh node short names to hex IDs using live, stored, and catalog sources."""

import logging

from .db_operations import (
    lookup_catalog_nodes_by_short_name,
    lookup_mesh_nodes_by_short_name,
)


def is_hex_node_id(value):
    ref = (value or "").strip()
    return ref.startswith("!")


def _node_entry(node_id, short_name, long_name=None, source=None):
    return {
        "num": node_id,
        "shortName": short_name or node_id,
        "longName": long_name or short_name or node_id,
        "source": source,
    }


def resolve_nodes_by_short_name(short_name, interface):
    """Return matching nodes from all resolution sources (deduped by hex id)."""
    short_name = (short_name or "").strip().lower()
    if not short_name:
        return []

    nodes = []
    seen = set()

    if interface is not None:
        for node_id, node in interface.nodes.items():
            user = node.get("user", {})
            name = user.get("shortName")
            if name and name.lower() == short_name:
                entry = _node_entry(
                    node_id, name, user.get("longName", name), "interface.nodes",
                )
                nodes.append(entry)
                seen.add(node_id)

    for db_node in lookup_mesh_nodes_by_short_name(short_name):
        if db_node["num"] not in seen:
            db_node["source"] = "mesh_nodes"
            nodes.append(db_node)
            seen.add(db_node["num"])

    manager = getattr(interface, "module_manager", None) if interface is not None else None
    if manager is not None:
        directory = manager.get_service("node_directory")
        if directory is not None:
            for db_node in directory.lookup_by_short_name(short_name):
                if db_node["num"] not in seen:
                    db_node["source"] = "node_info"
                    nodes.append(db_node)
                    seen.add(db_node["num"])

    for catalog_node in lookup_catalog_nodes_by_short_name(short_name):
        if catalog_node["num"] not in seen:
            catalog_node["source"] = "node_catalog"
            nodes.append(catalog_node)
            seen.add(catalog_node["num"])

    return nodes


def resolve_hex_node_id(node_ref, interface):
    """Resolve a hex id or short name to a canonical hex node id, if known."""
    ref = (node_ref or "").strip()
    if not ref:
        return None
    if is_hex_node_id(ref):
        return ref

    matches = resolve_nodes_by_short_name(ref, interface)
    if len(matches) == 1:
        return matches[0]["num"]
    return None


def normalize_sender_fields(sender_ref, sender_short_name, interface):
    sender_ref = (sender_ref or "").strip()
    sender_short_name = (sender_short_name or "").strip()

    if is_hex_node_id(sender_ref):
        hex_id = sender_ref
        if not sender_short_name and interface is not None:
            from .utils import get_node_short_name
            sender_short_name = get_node_short_name(hex_id, interface) or ""
        return hex_id, sender_short_name or hex_id

    if sender_ref and not sender_short_name:
        sender_short_name = sender_ref

    hex_id = resolve_hex_node_id(sender_short_name or sender_ref, interface)
    if hex_id:
        return hex_id, sender_short_name or sender_ref
    return sender_ref or sender_short_name, sender_short_name or sender_ref


def normalize_recipient_fields(recipient_ref, recipient_short_name, interface):
    recipient_ref = (recipient_ref or "").strip()
    recipient_short_name = (recipient_short_name or "").strip()

    if is_hex_node_id(recipient_ref):
        hex_id = recipient_ref
        if not recipient_short_name and interface is not None:
            from .utils import get_node_short_name
            recipient_short_name = get_node_short_name(hex_id, interface) or ""
        return hex_id, recipient_short_name or ""

    if recipient_ref and not recipient_short_name:
        recipient_short_name = recipient_ref

    hex_id = resolve_hex_node_id(recipient_short_name or recipient_ref, interface)
    return hex_id, recipient_short_name or recipient_ref


def recipient_mailbox_keys(recipient_hex, interface):
    """Return values that may appear in mail.recipient for this reader."""
    keys = []
    recipient_hex = (recipient_hex or "").strip()

    def _add_key(value):
        value = (value or "").strip()
        if value and value not in keys:
            keys.append(value)

    _add_key(recipient_hex)
    if interface is not None:
        from .utils import get_node_short_name
        _add_key(get_node_short_name(recipient_hex, interface))

    if recipient_hex:
        from .db_operations import get_db_connection, get_mesh_node

        mesh_node = get_mesh_node(recipient_hex)
        if mesh_node:
            _add_key(mesh_node[1])

        conn = get_db_connection()
        catalog_row = conn.execute(
            "SELECT short_name FROM node_catalog WHERE node_hex_username = ?",
            (recipient_hex,),
        ).fetchone()
        if catalog_row:
            _add_key(catalog_row[0])

    return keys


def record_mesh_node_from_interface(node_id, interface):
    if not node_id or interface is None:
        return
    from .db_operations import upsert_mesh_node

    node = interface.nodes.get(node_id)
    if not node:
        upsert_mesh_node(node_id)
        return
    user = node.get("user", {})
    upsert_mesh_node(
        node_id,
        user.get("shortName"),
        user.get("longName"),
        node.get("lastHeard"),
    )


def record_mesh_node_from_packet(packet, interface):
    """Record a node from any mesh packet (not only direct BBS messages)."""
    if not packet or interface is None:
        return
    node_id = packet.get("fromId")
    if not node_id:
        from .utils import get_node_id_from_num
        node_id = get_node_id_from_num(packet.get("from"), interface)
    if node_id:
        record_mesh_node_from_interface(node_id, interface)


def scan_mesh_nodes_store(interface):
    """Upsert all nodes currently known to the radio into mesh_nodes."""
    if interface is None:
        return
    try:
        for node_id, _node in dict(interface.nodes).items():
            if isinstance(node_id, str) and node_id.startswith("!"):
                record_mesh_node_from_interface(node_id, interface)
    except Exception as exc:
        logging.error("Error scanning mesh nodes store: %s", exc)
