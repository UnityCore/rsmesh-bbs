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


@dataclass
class ModuleSyncRegistration:
    module_id: int
    record_type: str
    wire_types: tuple[str, ...] = ()
    on_inbound_rs: Optional[ModuleInboundRsHandler] = None
    sync_pending: Optional[ModuleSyncPendingHandler] = None

    def normalized_wire_types(self) -> frozenset[str]:
        return frozenset((wire_type or "").strip().upper() for wire_type in self.wire_types if wire_type)


def get_pending_sync_peers(record_type: str, record_key: str, peers: list) -> list:
    from .db_operations import _get_pending_peers

    return _get_pending_peers(record_type, record_key, peers)


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
