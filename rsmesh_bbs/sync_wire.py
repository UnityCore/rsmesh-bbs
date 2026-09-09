"""RS sync wire-format helpers (peer labels: rsv1, rsv2, ...; on-wire prefix: RS)."""

import json
import logging
import time
import uuid

RS_WIRE_PREFIX = "RS"
RS_CHUNK_TYPE = "CHUNK"
SYNC_PACKET_MAX_LEN = 200
SYNC_CHUNK_TTL_SECONDS = 300

_KNOWN_RS_DECODERS = {1: "_decode_rs_v1"}


def rs_wire_version_for_protocol(sync_protocol):
    protocol = (sync_protocol or "").strip().lower()
    if protocol.startswith("rsv") and len(protocol) > 3:
        try:
            return int(protocol[3:])
        except ValueError:
            return None
    return None


def is_rs_sync_protocol(sync_protocol):
    return rs_wire_version_for_protocol(sync_protocol) is not None


def build_rs_message(wire_version, msg_type, data):
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"{RS_WIRE_PREFIX}|{wire_version}|{msg_type.upper()}|{payload}"


def parse_rs_envelope(message):
    parts = message.split("|", 3)
    if len(parts) < 4 or parts[0] != RS_WIRE_PREFIX:
        raise ValueError("Invalid RS sync message format")
    try:
        wire_version = int(parts[1])
    except ValueError:
        raise ValueError("Invalid RS sync message version") from None
    msg_type = parts[2].strip().upper()
    payload = parts[3]
    if not msg_type:
        raise ValueError("Invalid RS sync message type")
    return wire_version, msg_type, payload


def parse_rs_json_payload(payload):
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid RS sync JSON payload") from exc
    if not isinstance(data, dict):
        raise ValueError("Invalid RS sync JSON payload")
    return data


def _req_field(data, key, label):
    if key not in data:
        raise ValueError(f"Invalid RS sync payload: missing {label}")
    value = data[key]
    if value is None:
        raise ValueError(f"Invalid RS sync payload: missing {label}")
    return str(value)


def _opt_field(data, key, default=""):
    if key not in data or data[key] is None:
        return default
    return str(data[key])


def _decode_rs_v1(msg_type, data):
    msg_type = msg_type.upper()
    if msg_type == "BULLETIN":
        return msg_type, {
            "board": _req_field(data, "b", "board"),
            "sender_short_name": _req_field(data, "sn", "sender short name"),
            "subject": _opt_field(data, "sub"),
            "content": _opt_field(data, "body"),
            "unique_id": _req_field(data, "uid", "unique id"),
        }
    if msg_type == "MAIL":
        return msg_type, {
            "mail_sender_id": _opt_field(data, "s"),
            "sender_short_name": _req_field(data, "ssn", "sender short name"),
            "recipient_id": _opt_field(data, "r"),
            "recipient_short_name": _opt_field(data, "rsn"),
            "subject": _opt_field(data, "sub"),
            "content": _opt_field(data, "body"),
            "unique_id": _req_field(data, "uid", "unique id"),
        }
    if msg_type == "CHANNEL":
        return msg_type, {
            "channel_name": _req_field(data, "n", "channel name"),
            "channel_psk": _req_field(data, "psk", "channel psk"),
            "unique_id": _req_field(data, "uid", "unique id"),
        }
    if msg_type == "DELETE_BULLETIN":
        return msg_type, {"identifier": _req_field(data, "uid", "unique id")}
    if msg_type == "DELETE_MAIL":
        return msg_type, {"unique_id": _req_field(data, "uid", "unique id")}
    if msg_type == "DELETE_CHANNEL":
        return msg_type, {"unique_id": _req_field(data, "uid", "unique id")}
    if msg_type == "NODE":
        return msg_type, {
            "node_id": _req_field(data, "id", "node id"),
            "short_name": _opt_field(data, "sn"),
            "long_name": _opt_field(data, "ln"),
            "last_heard": _opt_field(data, "lh"),
        }
    raise ValueError(f"Unsupported RS sync message type: {msg_type}")


def _decode_rs_payload(wire_version, msg_type, payload):
    decoder_name = _KNOWN_RS_DECODERS.get(wire_version)
    if not decoder_name:
        raise ValueError(f"Unsupported RS sync wire version: {wire_version}")
    data = parse_rs_json_payload(payload)
    decoder = globals()[decoder_name]
    return decoder(msg_type, data)


def decode_rs_sync_message(message, sender_node_id=None):
    from .db_operations import get_sync_protocol_for_peer, note_rs_wire_version

    wire_version, msg_type, payload = parse_rs_envelope(message)
    configured = get_sync_protocol_for_peer(sender_node_id) or "tc2"
    expected = rs_wire_version_for_protocol(configured)

    note_rs_wire_version(sender_node_id, wire_version)

    versions_to_try = [wire_version]
    if expected is not None and expected not in versions_to_try:
        versions_to_try.append(expected)

    last_error = None
    for version in versions_to_try:
        try:
            decoded_type, fields = _decode_rs_payload(version, msg_type, payload)
            if version != wire_version:
                logging.info(
                    "Decoded RS sync message from %s using fallback wire version v%d "
                    "(received v%d, configured %s).",
                    sender_node_id,
                    version,
                    wire_version,
                    configured,
                )
            return decoded_type, fields
        except ValueError as exc:
            last_error = exc
    raise last_error or ValueError(f"Unsupported RS sync message: v{wire_version} {msg_type}")


def encode_bulletin_sync_message(sync_protocol, board, sender_short_name, subject, content, unique_id):
    if rs_wire_version_for_protocol(sync_protocol) == 1:
        return build_rs_message(
            1,
            "BULLETIN",
            {
                "b": board,
                "sn": sender_short_name,
                "sub": subject,
                "body": content,
                "uid": unique_id,
            },
        )
    return f"BULLETIN|{board}|{sender_short_name}|{subject}|{content}|{unique_id}"


def encode_mail_sync_message(
    sync_protocol,
    sender_id,
    sender_short_name,
    recipient_id,
    recipient_short_name,
    subject,
    content,
    unique_id,
):
    from .node_resolution import is_hex_node_id

    if rs_wire_version_for_protocol(sync_protocol) == 1:
        sender_hex = sender_id if is_hex_node_id(sender_id) else ""
        recipient_hex = recipient_id if is_hex_node_id(recipient_id) else ""
        return build_rs_message(
            1,
            "MAIL",
            {
                "s": sender_hex,
                "ssn": sender_short_name or "",
                "r": recipient_hex,
                "rsn": recipient_short_name or "",
                "sub": subject,
                "body": content,
                "uid": unique_id,
            },
        )

    wire_sender = sender_id if is_hex_node_id(sender_id) else (sender_short_name or sender_id or "")
    wire_recipient = (
        recipient_id
        if is_hex_node_id(recipient_id)
        else (recipient_short_name or recipient_id or "")
    )
    return (
        f"MAIL|{wire_sender}|{sender_short_name}|{wire_recipient}|"
        f"{subject}|{content}|{unique_id}"
    )


def encode_channel_sync_message(sync_protocol, name, psk, unique_id=None):
    if rs_wire_version_for_protocol(sync_protocol) == 1:
        if not unique_id:
            raise ValueError("RS channel sync requires unique_id")
        return build_rs_message(
            1,
            "CHANNEL",
            {"n": name, "psk": psk, "uid": unique_id},
        )
    return f"CHANNEL|{name}|{psk}"


def encode_delete_bulletin_sync_message(sync_protocol, bulletin_id, unique_id):
    if rs_wire_version_for_protocol(sync_protocol) == 1:
        if not unique_id:
            raise ValueError("RS delete bulletin sync requires unique_id")
        return build_rs_message(1, "DELETE_BULLETIN", {"uid": unique_id})
    return f"DELETE_BULLETIN|{bulletin_id}"


def encode_delete_mail_sync_message(sync_protocol, unique_id):
    if is_rs_sync_protocol(sync_protocol):
        wire_version = rs_wire_version_for_protocol(sync_protocol)
        return build_rs_message(wire_version, "DELETE_MAIL", {"uid": unique_id})
    return f"DELETE_MAIL|{unique_id}"


def encode_delete_channel_sync_message(sync_protocol, unique_id):
    wire_version = rs_wire_version_for_protocol(sync_protocol)
    if wire_version is None:
        raise ValueError("DELETE_CHANNEL sync is only supported for RS protocols")
    return build_rs_message(wire_version, "DELETE_CHANNEL", {"uid": unique_id})


def encode_node_sync_message(sync_protocol, node_id, short_name, long_name, last_heard):
    wire_version = rs_wire_version_for_protocol(sync_protocol)
    if wire_version is None:
        raise ValueError("NODE sync is only supported for RS protocols")
    return build_rs_message(
        wire_version,
        "NODE",
        {
            "id": node_id,
            "sn": short_name or "",
            "ln": long_name or short_name or "",
            "lh": "" if last_heard is None else str(last_heard),
        },
    )


def build_rs_chunk_message(wire_version, transfer_id, index, total, payload):
    return build_rs_message(
        wire_version,
        RS_CHUNK_TYPE,
        {
            "u": transfer_id,
            "i": index,
            "n": total,
            "p": payload,
        },
    )


def _chunk_packet_len(wire_version, transfer_id, index, total, payload):
    return len(build_rs_chunk_message(wire_version, transfer_id, index, total, payload))


def _max_chunk_payload(wire_version, transfer_id, index, total_placeholder, message, start, max_packet_len):
    remaining = len(message) - start
    if remaining <= 0:
        return 0

    low, high = 1, remaining
    best = 0
    while low <= high:
        mid = (low + high) // 2
        payload = message[start:start + mid]
        if _chunk_packet_len(wire_version, transfer_id, index, total_placeholder, payload) <= max_packet_len:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best


def build_rs_chunk_sequence(message, wire_version, max_packet_len=SYNC_PACKET_MAX_LEN):
    transfer_id = str(uuid.uuid4())
    size_placeholder = 99
    fragments = []
    start = 0
    while start < len(message):
        payload_len = _max_chunk_payload(
            wire_version,
            transfer_id,
            len(fragments),
            size_placeholder,
            message,
            start,
            max_packet_len,
        )
        if payload_len <= 0:
            raise ValueError("Sync message cannot be encoded into RS chunk packets")
        fragments.append(message[start:start + payload_len])
        start += payload_len

    total = len(fragments)
    packets = [
        build_rs_chunk_message(wire_version, transfer_id, index, total, payload)
        for index, payload in enumerate(fragments)
    ]
    for packet in packets:
        if len(packet) > max_packet_len:
            raise ValueError("RS sync chunk packet exceeds mesh packet limit")
    return packets


def plan_sync_transmit_packets(message, sync_protocol, max_packet_len=SYNC_PACKET_MAX_LEN):
    if len(message) <= max_packet_len:
        return [message]
    if not is_rs_sync_protocol(sync_protocol):
        logging.warning(
            "Sync message length %s exceeds mesh packet limit (%s) for protocol %s",
            len(message),
            max_packet_len,
            sync_protocol,
        )
        return None
    wire_version = rs_wire_version_for_protocol(sync_protocol)
    try:
        return build_rs_chunk_sequence(message, wire_version, max_packet_len)
    except ValueError as exc:
        logging.error("Failed to build RS sync chunk sequence: %s", exc)
        return None


def parse_rs_chunk_payload(payload):
    data = parse_rs_json_payload(payload)
    transfer_id = data.get("u")
    if not transfer_id:
        raise ValueError("Invalid RS chunk payload: missing transfer id")
    try:
        index = int(data["i"])
        total = int(data["n"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid RS chunk payload: missing chunk index") from None
    if total <= 0 or index < 0 or index >= total:
        raise ValueError("Invalid RS chunk payload: chunk bounds")
    payload_part = data.get("p")
    if payload_part is None:
        raise ValueError("Invalid RS chunk payload: missing chunk data")
    return str(transfer_id), index, total, str(payload_part)


class SyncChunkAssembler:
    def __init__(self, ttl_seconds=SYNC_CHUNK_TTL_SECONDS):
        self._ttl_seconds = ttl_seconds
        self._pending = {}

    def _purge_expired(self):
        if not self._pending:
            return
        cutoff = time.time() - self._ttl_seconds
        expired = [key for key, entry in self._pending.items() if entry["updated_at"] < cutoff]
        for key in expired:
            del self._pending[key]

    def add_chunk(self, sender_node_id, transfer_id, index, total, payload):
        self._purge_expired()
        key = (sender_node_id, transfer_id)
        entry = self._pending.get(key)
        if entry is None:
            entry = {
                "total": total,
                "parts": {},
                "updated_at": time.time(),
            }
            self._pending[key] = entry
        elif entry["total"] != total:
            logging.warning(
                "RS chunk sequence mismatch for %s transfer %s; discarding partial message.",
                sender_node_id,
                transfer_id,
            )
            entry = {"total": total, "parts": {}, "updated_at": time.time()}
            self._pending[key] = entry

        entry["parts"][index] = payload
        entry["updated_at"] = time.time()
        if len(entry["parts"]) < total:
            return None

        for chunk_index in range(total):
            if chunk_index not in entry["parts"]:
                return None

        message = "".join(entry["parts"][chunk_index] for chunk_index in range(total))
        del self._pending[key]
        return message

