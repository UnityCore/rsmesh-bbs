"""Module sync registration API and record_sync_peers helpers (Phase A, rsv1 only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

CORE_SYNC_PREFIXES = (
    "RS|",
    "BULLETIN|",
    "MAIL|",
    "DELETE_BULLETIN|",
    "DELETE_MAIL|",
    "CHANNEL|",
)

_CORE_RS_WIRE_TYPES = frozenset({
    "BULLETIN",
    "MAIL",
    "CHANNEL",
    "NODE",
    "DELETE_BULLETIN",
    "DELETE_MAIL",
    "DELETE_CHANNEL",
    "CHUNK",
})

ModuleInboundRsHandler = Callable[[str, dict[str, Any], str, Any], None]
ModuleSyncPendingHandler = Callable[[list, Any], None]
ModuleListUnsyncedHandler = Callable[[], list[tuple[str, str]]]


@dataclass
class ModuleSyncRegistration:
    module_id: int
    record_type: str
    wire_types: tuple[str, ...] = ()
    on_inbound_rs: Optional[ModuleInboundRsHandler] = None
    sync_pending: Optional[ModuleSyncPendingHandler] = None
    list_unsynced: Optional[ModuleListUnsyncedHandler] = None

    def normalized_wire_types(self) -> frozenset[str]:
        return frozenset((wire_type or "").strip().upper() for wire_type in self.wire_types if wire_type)


def get_registered_module_sync_rows():
    """Return (registration, module_row) pairs for modules with sync hooks loaded."""
    from types import SimpleNamespace

    from .db_operations import get_module_by_id
    from .module_loader import ModuleManager

    manager = ModuleManager()
    interface = SimpleNamespace(module_manager=manager)
    manager.load_modules(interface)
    rows = []
    for registration in manager.get_sync_registrations():
        module_row = get_module_by_id(registration.module_id)
        if module_row is None:
            continue
        rows.append((registration, module_row))
    return sorted(rows, key=lambda item: (item[1][1] or "").lower())


def module_id_for_record_type(record_type: str, interface) -> Optional[int]:
    if not (record_type or "").startswith("module:"):
        return None
    manager = getattr(interface, "module_manager", None) if interface is not None else None
    if manager is None:
        return None
    for registration in manager.get_sync_registrations():
        if registration.record_type == record_type:
            return registration.module_id
    return None


def get_module_unsynced_records(interface=None) -> list[tuple[str, str, str, list[str]]]:
    """Return (module_name, record_key, label, pending_peer_labels) for pending module sync."""
    from types import SimpleNamespace

    from .db_operations import _get_pending_peer_labels, get_module_by_id, get_sync_peers
    from .module_loader import ModuleManager

    if interface is None:
        manager = ModuleManager()
        interface = SimpleNamespace(module_manager=manager)
        manager.load_modules(interface)
    else:
        manager = getattr(interface, "module_manager", None)

    if manager is None:
        return []

    peers = get_sync_peers()
    rows = []
    for registration in manager.get_sync_registrations():
        if not manager.is_module_sync_enabled(registration.module_id):
            continue
        if registration.list_unsynced is None:
            continue
        module_row = get_module_by_id(registration.module_id)
        module_name = module_row[1] if module_row else f"Module {registration.module_id}"
        try:
            unsynced_items = registration.list_unsynced() or []
        except Exception as exc:
            import logging
            logging.error(
                "Module %s list_unsynced failed: %s",
                registration.module_id,
                exc,
                exc_info=True,
            )
            continue
        for record_key, label in unsynced_items:
            record_key = (record_key or "").strip()
            if not record_key:
                continue
            pending = _get_pending_peer_labels(
                registration.record_type,
                record_key,
                peers,
                interface,
            )
            if not pending:
                continue
            rows.append((module_name, record_key, label or record_key, pending))
    return sorted(rows, key=lambda item: (item[0].lower(), item[1]))


def get_pending_sync_peers(record_type: str, record_key: str, peers: list, interface=None) -> list:
    from .db_operations import _get_pending_peers

    return _get_pending_peers(record_type, record_key, peers, interface)


def mark_sync_peers_synced(record_type: str, record_key: str, peers_or_ids) -> None:
    from .db_operations import _mark_peers_synced, _resolve_peer_id

    peer_ids = []
    for item in peers_or_ids or []:
        if isinstance(item, int):
            peer_ids.append(item)
            continue
        peer_id = _resolve_peer_id(item)
        if peer_id is not None:
            peer_ids.append(peer_id)
    _mark_peers_synced(record_type, record_key, peer_ids)


def reset_record_sync_peers(record_type: str, record_key: str) -> None:
    from .db_operations import _reset_record_peer_sync

    _reset_record_peer_sync(record_type, record_key)


def decode_module_rs_payload(message: str) -> tuple[int, str, dict[str, Any]]:
    from .sync_wire import parse_rs_envelope, parse_rs_json_payload

    wire_version, msg_type, payload = parse_rs_envelope(message)
    return wire_version, msg_type, parse_rs_json_payload(payload)
