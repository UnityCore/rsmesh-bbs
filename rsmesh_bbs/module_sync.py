"""Module sync registration API and record_sync_peers helpers (Phase A, rsv1 only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

_WIRE_SUFFIX_RE = re.compile(r"^[A-Z0-9_]{1,16}$")

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
ModuleSyncStatusLinesHandler = Callable[["ModuleSyncStatus"], list[str]]


@dataclass(frozen=True)
class ModuleSyncPeerPending:
    peer_id: int
    bbs_node: str
    bbs_name: str
    sync_out: str
    ingest_in: str


@dataclass(frozen=True)
class ModuleSyncRecordStatus:
    record_key: str
    label: str
    pending_peers: tuple[ModuleSyncPeerPending, ...]


@dataclass(frozen=True)
class ModuleSyncStatus:
    module_id: int
    module_name: str
    module_dir: str
    record_type: str
    sync_enabled: bool
    pending_record_count: int
    pending_peer_count: int
    records: tuple[ModuleSyncRecordStatus, ...]


def normalize_module_wire_prefix(module_dir: str) -> str:
    text = (module_dir or "").strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def normalize_wire_suffix(suffix: str) -> Optional[str]:
    text = (suffix or "").strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text or not _WIRE_SUFFIX_RE.match(text):
        return None
    return text


def build_module_wire_type(module_dir: str, suffix: str) -> Optional[str]:
    prefix = normalize_module_wire_prefix(module_dir)
    normalized_suffix = normalize_wire_suffix(suffix)
    if not prefix or not normalized_suffix:
        return None
    return f"{prefix}_{normalized_suffix}"


def expected_module_record_type(module_dir: str) -> str:
    return f"module:{(module_dir or '').strip()}"


def normalize_legacy_wire_type(wire_type: str) -> Optional[str]:
    text = (wire_type or "").strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text or not _WIRE_SUFFIX_RE.match(text):
        return None
    return text


@dataclass
class ModuleSyncRegistration:
    module_id: int
    record_type: str
    wire_suffixes: tuple[str, ...] = ()
    legacy_wire_types: tuple[str, ...] = ()
    on_inbound_rs: Optional[ModuleInboundRsHandler] = None
    sync_pending: Optional[ModuleSyncPendingHandler] = None
    list_unsynced: Optional[ModuleListUnsyncedHandler] = None
    sync_status_lines: Optional[ModuleSyncStatusLinesHandler] = None

    def iter_registered_wire_types(self, module_dir: str):
        seen = set()
        for suffix in self.wire_suffixes:
            wire_type = build_module_wire_type(module_dir, suffix)
            if wire_type and wire_type not in seen:
                seen.add(wire_type)
                yield wire_type
        for legacy in self.legacy_wire_types:
            wire_type = normalize_legacy_wire_type(legacy)
            if wire_type and wire_type not in seen:
                seen.add(wire_type)
                yield wire_type


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


def format_sync_alerts_summary(rs_version_count, module_peer_count=0):
    rs_noun = "peer" if rs_version_count == 1 else "peers"
    module_noun = "peer" if module_peer_count == 1 else "peers"
    return (
        f"Sync alerts: RS version: {rs_version_count} {rs_noun}, "
        f"Modules: {module_peer_count} {module_noun}"
    )


def count_module_sync_alert_peers(interface=None) -> int:
    """Distinct sync peers with at least one pending module-owned record."""
    pending_peer_ids = set()
    for status in _iter_module_sync_statuses(interface):
        for record in status.records:
            for peer in record.pending_peers:
                pending_peer_ids.add(peer.peer_id)
    return len(pending_peer_ids)


def get_module_sync_status(module_id, interface=None) -> Optional[ModuleSyncStatus]:
    """Return sync status details for a module developer admin screen."""
    for status in _iter_module_sync_statuses(interface):
        if status.module_id == int(module_id):
            return status
    return None


def get_module_sync_status_lines(module_id, interface=None) -> list[str]:
    """Return display lines for a module sync status screen."""
    status = get_module_sync_status(module_id, interface)
    if status is None:
        return []

    registration = _registration_for_module(module_id, interface)
    if registration is not None and registration.sync_status_lines is not None:
        try:
            return list(registration.sync_status_lines(status) or [])
        except Exception as exc:
            import logging

            logging.error(
                "Module %s sync_status_lines failed: %s",
                module_id,
                exc,
                exc_info=True,
            )

    return _default_module_sync_status_lines(status)


def _registration_for_module(module_id, interface):
    manager = _module_manager(interface)
    if manager is None:
        return None
    module_id = int(module_id)
    for registration in manager.get_sync_registrations():
        if registration.module_id == module_id:
            return registration
    return None


def _module_manager(interface):
    if interface is not None:
        return getattr(interface, "module_manager", None)
    from types import SimpleNamespace

    from .module_loader import ModuleManager

    manager = ModuleManager()
    manager.load_modules(SimpleNamespace(module_manager=manager))
    return manager


def _iter_module_sync_statuses(interface=None):
    from .db_operations import (
        _resolve_peer_id,
        get_module_by_id,
        get_sync_peer_module_flags,
        get_sync_peers,
    )

    manager = _module_manager(interface)
    if manager is None:
        return

    peers = get_sync_peers()
    for registration in manager.get_sync_registrations():
        module_row = get_module_by_id(registration.module_id)
        if module_row is None:
            continue
        module_name = module_row[1]
        module_dir = module_row[2]
        sync_enabled = manager.is_module_sync_enabled(registration.module_id)
        records = []
        pending_peer_ids = set()

        if sync_enabled and registration.list_unsynced is not None:
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
                unsynced_items = []

            for record_key, label in unsynced_items:
                record_key = (record_key or "").strip()
                if not record_key:
                    continue
                pending_peers = []
                for peer in get_pending_sync_peers(
                    registration.record_type,
                    record_key,
                    peers,
                    interface,
                ):
                    peer_id = _resolve_peer_id(peer)
                    if peer_id is None:
                        continue
                    sync_out, ingest_in = get_sync_peer_module_flags(
                        peer_id,
                        registration.module_id,
                    )
                    pending_peers.append(
                        ModuleSyncPeerPending(
                            peer_id=peer_id,
                            bbs_node=peer[1],
                            bbs_name=(peer[2] or "") if len(peer) > 2 else "",
                            sync_out=sync_out,
                            ingest_in=ingest_in,
                        )
                    )
                    pending_peer_ids.add(peer_id)
                if pending_peers:
                    records.append(
                        ModuleSyncRecordStatus(
                            record_key=record_key,
                            label=label or record_key,
                            pending_peers=tuple(pending_peers),
                        )
                    )

        yield ModuleSyncStatus(
            module_id=registration.module_id,
            module_name=module_name,
            module_dir=module_dir,
            record_type=registration.record_type,
            sync_enabled=sync_enabled,
            pending_record_count=len(records),
            pending_peer_count=len(pending_peer_ids),
            records=tuple(records),
        )


def _default_module_sync_status_lines(status: ModuleSyncStatus) -> list[str]:
    lines = [
        f"Module: {status.module_name}",
        f"Record type: {status.record_type}",
        f"Sync enabled: {'Y' if status.sync_enabled else 'N'}",
        f"Pending records: {status.pending_record_count}",
        f"Pending peers: {status.pending_peer_count}",
    ]
    if not status.records:
        lines.append("No pending module sync records.")
        return lines

    for record in status.records:
        lines.append(f"Record {record.record_key}: {record.label}")
        peer_labels = []
        for peer in record.pending_peers:
            name = peer.bbs_name or peer.bbs_node
            flags = []
            if peer.sync_out != "Y":
                flags.append("out=N")
            if peer.ingest_in != "Y":
                flags.append("in=N")
            suffix = f" ({', '.join(flags)})" if flags else ""
            peer_labels.append(f"{name}{suffix}")
        lines.append("  Pending peers: " + ", ".join(peer_labels))
    return lines


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
