"""Type metadata and validation for sys_config admin editors."""

from __future__ import annotations

import re
from typing import Any, Optional

from .config_init import parse_config_value, stringify_config_value

_NODE_ID_RE = re.compile(r"^![0-9a-fA-F]{8}$")
_SHORT_NAME_RE = re.compile(r"^.{1,4}$")

SYS_CONFIG_FIELD_SPECS: dict[tuple[str, str], dict[str, Any]] = {
    ("bbs", "board_name"): {"type": "string", "min_len": 1, "max_len": 64},
    ("bbs", "eventbus_topic"): {"type": "string", "min_len": 1, "max_len": 128},
    ("bbs", "send_urgent_alert_local"): {"type": "bool"},
    ("bbs", "send_urgent_alert_from_sync"): {"type": "bool"},
    ("bbs", "superuser_node"): {"type": "node_id"},
    ("interface", "type"): {"type": "enum", "values": ("serial", "tcp")},
    ("interface", "port"): {"type": "string", "max_len": 128},
    ("interface", "hostname"): {"type": "string", "max_len": 255},
    ("interface", "node_id"): {"type": "node_id"},
    ("interface", "short_name"): {"type": "short_name"},
    ("interface", "long_name"): {"type": "string", "max_len": 40},
    ("schedule", "peer_sync_minutes"): {"type": "int", "min": 1},
    ("schedule", "module_exec_minutes"): {"type": "int", "min": 1},
    ("schedule", "sync_purge_minutes"): {"type": "int", "min": 1},
    ("schedule", "bulletin_display_age_days"): {"type": "int", "min": 0},
}


def get_field_spec(cfg_section: str, cfg_key: str) -> dict[str, Any]:
    return dict(SYS_CONFIG_FIELD_SPECS.get((cfg_section, cfg_key), {"type": "string"}))


def _normalize_bool_text(value: Any) -> str:
    parsed = parse_config_value(value)
    if isinstance(parsed, bool):
        return "true" if parsed else "false"
    text = str(value or "").strip().lower()
    if text in {"y", "yes", "true", "1"}:
        return "true"
    if text in {"n", "no", "false", "0"}:
        return "false"
    return text


def bool_value_to_yn(value: Any) -> str:
    return "Y" if parse_config_value(value) is True else "N"


def _validate_node_id(value: str) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return ""
    if not _NODE_ID_RE.match(text):
        return None
    return text.lower()


def _validate_short_name(value: str) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return ""
    if not _SHORT_NAME_RE.match(text):
        return None
    return text


def validate_sys_config_value(
    cfg_section: str,
    cfg_key: str,
    value: Any,
) -> tuple[bool, str, Optional[str]]:
    spec = get_field_spec(cfg_section, cfg_key)
    field_type = spec.get("type", "string")

    if field_type == "bool":
        normalized = _normalize_bool_text(value)
        if normalized not in {"true", "false"}:
            return False, "", "Enter Y or N."
        return True, normalized, None

    if field_type == "enum":
        text = str(value or "").strip().lower()
        allowed = tuple(str(item).lower() for item in spec.get("values", ()))
        if text not in allowed:
            return False, "", f"Value must be one of: {', '.join(allowed)}."
        return True, text, None

    if field_type == "int":
        text = str(value or "").strip()
        try:
            number = int(text)
        except (TypeError, ValueError):
            return False, "", "Enter a whole number."
        minimum = spec.get("min")
        if minimum is not None and number < minimum:
            return False, "", f"Value must be at least {minimum}."
        return True, str(number), None

    if field_type == "node_id":
        normalized = _validate_node_id(str(value or ""))
        if normalized is None:
            return False, "", "Node ID must be empty or ! followed by 8 hex digits."
        return True, normalized, None

    if field_type == "short_name":
        normalized = _validate_short_name(str(value or ""))
        if normalized is None:
            return False, "", "Short name must be empty or 1-4 characters."
        return True, normalized, None

    text = str(value if value is not None else "").strip()
    min_len = spec.get("min_len")
    max_len = spec.get("max_len")
    if min_len is not None and len(text) < min_len:
        return False, "", f"Value must be at least {min_len} characters."
    if max_len is not None and len(text) > max_len:
        return False, "", f"Value must be at most {max_len} characters."
    return True, text, None


def format_stored_sys_config_value(cfg_section: str, cfg_key: str, value: Any) -> str:
    spec = get_field_spec(cfg_section, cfg_key)
    if spec.get("type") == "bool":
        return _normalize_bool_text(value)
    valid, normalized, _error = validate_sys_config_value(cfg_section, cfg_key, value)
    if not valid:
        return stringify_config_value(value)
    return normalized if normalized is not None else ""
