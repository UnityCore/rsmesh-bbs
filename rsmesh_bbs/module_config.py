"""Module-scoped sys_config access (one section per module directory)."""

from __future__ import annotations

import re
from typing import Any, Optional

from .config_init import parse_config_value, stringify_config_value
from .db_operations import add_sys_config_entry, get_sys_config_value

_MODULE_CONFIG_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def module_config_section(module_dir: str) -> str:
    return f"module:{(module_dir or '').strip()}"


def validate_module_config_key(key: str) -> bool:
    return bool(_MODULE_CONFIG_KEY_RE.match((key or "").strip()))


def ensure_module_config_value(module_dir: str, key: str, default: Any) -> str:
    section = module_config_section(module_dir)
    existing = get_sys_config_value(section, key)
    if existing is not None:
        return existing
    stored = stringify_config_value(default)
    add_sys_config_entry(section, key, stored)
    return stored


def get_module_config_value(module_dir: str, key: str, default: Any = None) -> Any:
    if not validate_module_config_key(key):
        raise ValueError(f"Invalid module config key: {key}")
    section = module_config_section(module_dir)
    value = get_sys_config_value(section, key)
    if value is None:
        return default
    return parse_config_value(value)


def set_module_config_value(module_dir: str, key: str, value: Any) -> bool:
    from .db_operations import update_sys_config_entry

    if not validate_module_config_key(key):
        return False
    section = module_config_section(module_dir)
    stored = stringify_config_value(value)
    if get_sys_config_value(section, key) is None:
        return add_sys_config_entry(section, key, stored)
    return update_sys_config_entry(section, key, stored)
