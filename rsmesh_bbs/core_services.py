"""Core BBS service toggles (bulletins, mail, channels)."""

from pathlib import Path

import yaml

from .config_init import DEFAULT_CONFIG_FILE, load_config, parse_config_value
from .db_operations import add_sys_config_entry, get_sys_config_value, update_sys_config_entry

CFG_SECTION = "bbs"

CORE_BULLETINS_KEY = "core_bulletins"
CORE_MAIL_KEY = "core_mail"
CORE_CHANNELS_KEY = "core_channels"

CORE_SERVICE_KEYS = (CORE_BULLETINS_KEY, CORE_MAIL_KEY, CORE_CHANNELS_KEY)

CORE_SERVICE_LABELS = {
    CORE_BULLETINS_KEY: "Bulletins",
    CORE_MAIL_KEY: "Mail",
    CORE_CHANNELS_KEY: "Channels",
}

MAIN_MENU_HANDLER_KEYS = {
    "b": CORE_BULLETINS_KEY,
    "c": CORE_CHANNELS_KEY,
    "m": CORE_MAIL_KEY,
}


def _core_service_bool(cfg_key, default=True):
    value = get_sys_config_value(CFG_SECTION, cfg_key)
    if value is None:
        return default
    return parse_config_value(value) is True


def is_core_bulletins_enabled():
    return _core_service_bool(CORE_BULLETINS_KEY)


def is_core_mail_enabled():
    return _core_service_bool(CORE_MAIL_KEY)


def is_core_channels_enabled():
    return _core_service_bool(CORE_CHANNELS_KEY)


def is_core_service_enabled(cfg_key):
    if cfg_key == CORE_BULLETINS_KEY:
        return is_core_bulletins_enabled()
    if cfg_key == CORE_MAIL_KEY:
        return is_core_mail_enabled()
    if cfg_key == CORE_CHANNELS_KEY:
        return is_core_channels_enabled()
    raise ValueError(f"Unknown core service key: {cfg_key}")


def get_core_service_states():
    return {key: is_core_service_enabled(key) for key in CORE_SERVICE_KEYS}


def _regenerate_main_menu():
    from .mesh_ui import regenerate_main_menu_file

    regenerate_main_menu_file()


def set_core_service_enabled(cfg_key, enabled):
    if cfg_key not in CORE_SERVICE_KEYS:
        raise ValueError(f"Unknown core service key: {cfg_key}")
    value = "true" if enabled else "false"
    if get_sys_config_value(CFG_SECTION, cfg_key) is None:
        add_sys_config_entry(CFG_SECTION, cfg_key, value)
    else:
        update_sys_config_entry(CFG_SECTION, cfg_key, value)
    _regenerate_main_menu()


def toggle_core_service(cfg_key):
    set_core_service_enabled(cfg_key, not is_core_service_enabled(cfg_key))


def ensure_core_services_config(config_file=None):
    """Seed missing core-service keys in sys_config and config.yml (default enabled)."""
    config_file = config_file or DEFAULT_CONFIG_FILE
    path = Path(config_file)

    for key in CORE_SERVICE_KEYS:
        if get_sys_config_value(CFG_SECTION, key) is None:
            add_sys_config_entry(CFG_SECTION, key, "true")

    if path.is_file():
        config = load_config(config_file)
        bbs = config.setdefault("bbs", {})
        yaml_updated = False
        for key in CORE_SERVICE_KEYS:
            if key not in bbs:
                bbs[key] = True
                yaml_updated = True
        if yaml_updated:
            with path.open("w", encoding="utf-8") as handle:
                yaml.dump(config, handle, default_flow_style=False, sort_keys=False)

    _regenerate_main_menu()
