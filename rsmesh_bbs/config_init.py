import argparse
import sys
import time
from pathlib import Path
from typing import Any, Optional

import meshtastic.stream_interface
import meshtastic.serial_interface
import meshtastic.tcp_interface
import serial.tools.list_ports
import yaml

from .version import APP_NAME, VERSION

DEFAULT_CONFIG_FILE = "config.yml"
DEFAULT_CLIENT_CONFIG_FILE = "config_client.yml"
EXAMPLE_CONFIG_FILE = "example_config.yml"

_APP_ROOT = Path(__file__).resolve().parent.parent

SYS_CONFIG_SECTION_LABELS = {
    "bbs": "BBS",
    "interface": "Interface",
    "schedule": "Schedule",
}

# Keys managed on other admin screens; still required in sys_config but hidden here.
SYS_CONFIG_ADMIN_EXCLUDED_KEYS = frozenset({
    ("bbs", "core_bulletins"),
    ("bbs", "core_mail"),
    ("bbs", "core_channels"),
    ("bbs", "mail_commands_on_main_menu"),
    ("bbs", "suppress_modules_menu"),
})


def require_config_file(config_file: Optional[str] = None) -> str:
    path = Path(config_file or DEFAULT_CONFIG_FILE)
    if not path.is_file():
        print(f"Error: configuration file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return str(path)


def require_client_config_file(client_config_file: Optional[str] = None) -> str:
    path = Path(client_config_file or DEFAULT_CLIENT_CONFIG_FILE)
    if not path.is_file():
        print(f"Error: client configuration file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return str(path)


def client_setup_paths(
    config_file: Optional[str] = None,
    client_config_file: Optional[str] = None,
) -> tuple[Path, Path]:
    config_path = Path(config_file or DEFAULT_CONFIG_FILE)
    client_path = Path(client_config_file or DEFAULT_CLIENT_CONFIG_FILE)
    return config_path, client_path


def missing_client_setup_files(
    config_file: Optional[str] = None,
    client_config_file: Optional[str] = None,
) -> list[str]:
    config_path, client_path = client_setup_paths(config_file, client_config_file)
    return [str(path) for path in (config_path, client_path) if not path.is_file()]


def print_incomplete_setup_error(missing: list[str]) -> None:
    print("Error: board setup is incomplete.", file=sys.stderr)
    if len(missing) == 1:
        print(f"Missing configuration file: {missing[0]}", file=sys.stderr)
    else:
        print("Missing configuration files:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)


def require_client_setup(
    config_file: Optional[str] = None,
    client_config_file: Optional[str] = None,
) -> tuple[str, str]:
    """Ensure BBS and client config files exist before starting the mesh client."""
    missing = missing_client_setup_files(config_file, client_config_file)
    if missing:
        print_incomplete_setup_error(missing)
        raise SystemExit(1)
    config_path, client_path = client_setup_paths(config_file, client_config_file)
    return str(config_path), str(client_path)


def load_client_config(client_config_file: Optional[str] = None) -> dict[str, Any]:
    if client_config_file is None:
        client_config_file = DEFAULT_CLIENT_CONFIG_FILE
    return load_config(client_config_file)


def get_client_settings(client_config_file: Optional[str] = None) -> dict[str, str]:
    from .mesh_client import (
        DEFAULT_CLIENT_LONG_NAME,
        DEFAULT_CLIENT_NODE_ID,
        DEFAULT_CLIENT_SHORT_NAME,
    )

    config = load_client_config(client_config_file)
    client = config.get("client", {})
    return {
        "node_id": client.get("node_id", DEFAULT_CLIENT_NODE_ID),
        "short_name": client.get("short_name", DEFAULT_CLIENT_SHORT_NAME),
        "long_name": client.get("long_name", DEFAULT_CLIENT_LONG_NAME),
    }


def load_config(config_file: Optional[str] = None) -> dict[str, Any]:
    if config_file is None:
        config_file = DEFAULT_CONFIG_FILE
    path = Path(config_file)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def stringify_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def get_example_config_path() -> Path:
    return _APP_ROOT / EXAMPLE_CONFIG_FILE


def load_example_config_defaults() -> list[tuple[str, str, str]]:
    path = get_example_config_path()
    if not path.is_file():
        raise FileNotFoundError(f"Example configuration file not found: {path}")
    return flatten_yaml_config(load_config(str(path)))


def get_sys_config_schema() -> dict[str, list[str]]:
    """Ordered section -> keys from example_config.yml."""
    schema: dict[str, list[str]] = {}
    for cfg_section, cfg_key, _cfg_value in load_example_config_defaults():
        schema.setdefault(cfg_section, []).append(cfg_key)
    return schema


def get_sys_config_admin_schema() -> dict[str, list[str]]:
    """Schema keys exposed under Administration -> System Configuration."""
    schema = {}
    for cfg_section, keys in get_sys_config_schema().items():
        admin_keys = [
            key for key in keys
            if (cfg_section, key) not in SYS_CONFIG_ADMIN_EXCLUDED_KEYS
        ]
        if admin_keys:
            schema[cfg_section] = admin_keys
    return schema


def flatten_yaml_config(config: dict[str, Any]) -> list[tuple[str, str, str]]:
    entries = []
    for section, values in config.items():
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if value is None:
                continue
            entries.append((section, key, stringify_config_value(value)))
    return entries


def build_ordered_config_from_entries(
    entries: list[tuple[str, str, str]],
    schema: Optional[dict[str, list[str]]] = None,
) -> dict[str, Any]:
    """Build a config dict using schema key order; omit keys outside the schema."""
    schema = schema or get_sys_config_schema()
    values = {(section, key): value for section, key, value in entries}
    config: dict[str, Any] = {}
    for section, keys in schema.items():
        section_values = {}
        for key in keys:
            pair = (section, key)
            if pair in values:
                section_values[key] = parse_config_value(values[pair])
        if section_values:
            config[section] = section_values
    return config


def parse_config_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    lower = text.lower()
    if lower == 'true':
        return True
    if lower == 'false':
        return False
    if text.isdigit() or (text.startswith('-') and text[1:].isdigit()):
        return int(text)
    try:
        if '.' in text:
            return float(text)
    except ValueError:
        pass
    return text


def build_config_from_sys_config_entries(entries: list[tuple[str, str, str]]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for cfg_section, cfg_key, cfg_value in entries:
        section = config.setdefault(cfg_section, {})
        section[cfg_key] = parse_config_value(cfg_value)
    return config


def export_sys_config_to_yaml(entries: list[tuple[str, str, str]], config_file: Optional[str] = None) -> str:
    path = Path(config_file or DEFAULT_CONFIG_FILE)
    config = build_ordered_config_from_entries(entries)
    with path.open('w', encoding='utf-8') as handle:
        yaml.dump(config, handle, default_flow_style=False, sort_keys=False)
    return str(path)


def ensure_config_yaml_schema(config_file: Optional[str] = None) -> bool:
    """Add missing example_config.yml keys to config.yml without overwriting values."""
    config_file = config_file or DEFAULT_CONFIG_FILE
    path = Path(config_file)
    if not path.is_file():
        return False
    config = load_config(str(path))
    example = load_config(str(get_example_config_path()))
    updated = False
    for section, values in example.items():
        if not isinstance(values, dict):
            continue
        section_dict = config.setdefault(section, {})
        for key, default_value in values.items():
            if key not in section_dict:
                section_dict[key] = default_value
                updated = True
    if updated:
        with path.open("w", encoding="utf-8") as handle:
            yaml.dump(config, handle, default_flow_style=False, sort_keys=False)
    return updated


def init_cli_parser() -> argparse.Namespace:
    """Parse server CLI arguments."""
    parser = argparse.ArgumentParser(description=f"{APP_NAME} system")
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"{APP_NAME} {VERSION}",
    )
    parser.add_argument(
        "--config", "-c",
        action="store",
        help="Path to system configuration file (default: config.yml)",
        default=None,
    )
    return parser.parse_args()


def get_board_name(config_file: Optional[str] = None) -> str:
    config = load_config(config_file)
    bbs = config.get('bbs', {})
    return bbs.get('board_name', 'RSNetwork BBS')


def format_board_banner(board_name: str, footer: str = None) -> str:
    border = '-' * len(board_name)
    banner = f"\n{border}\n{board_name}\n{border}\n"
    if footer:
        banner += f"\n{footer}\n"
    else:
        banner += "\n"
    return banner


def initialize_config(config_file: Optional[str] = None) -> dict[str, Any]:
    """
    Function reads and parses system configuration file

    Returns a dict with the following entries:
    config - parsed config file
    interface_type - type of the active interface
    hostname - host name for TCP interface
    port - serial port name for serial interface

    Args:
        config_file (str, optional): Path to config file. Function reads from './config.yml' if this arg is set to None. Defaults to None.

    Returns:
        dict: dict with system configuration, ad described above
    """
    config = load_config(config_file)

    interface = config.get('interface', {})
    bbs = config.get('bbs', {})

    interface_type = interface.get('type')
    if not interface_type:
        raise KeyError("interface.type is required in the configuration file")

    hostname = interface.get('hostname')
    port = interface.get('port')

    superuser_node = (bbs.get('superuser_node') or '').strip()
    board_name = bbs.get('board_name', 'RSNetwork BBS')

    return {
        'config': config,
        'interface_type': interface_type,
        'hostname': hostname,
        'port': port,
        'superuser_node': superuser_node,
        'board_name': board_name,
    }


def get_interface(system_config: dict[str, Any]) -> meshtastic.stream_interface.StreamInterface:
    """
    Function opens and returns an instance meshtastic interface of type specified by the configuration

    Function creates and returns an instance of a class inheriting from meshtastic.stream_interface.StreamInterface.
    The type of the class depends on the type of the interface specified by the system configuration.
    For 'serial' interfaces, function returns an instance of meshtastic.serial_interface.SerialInterface,
    and for 'tcp' interface, an instance of meshtastic.tcp_interface.TCPInterface.

    Args:
        system_config (dict[str, Any]): A dict with system configuration. See description of initialize_config() for details.

    Raises:
        ValueError: Exception raised in the following cases:
                - Type of interface not provided in the system config
                - Multiple serial ports present in the system, and no port specified in the configuration
                - Serial port interface requested, but no ports found in the system
                - Hostname not provided for TCP interface

    Returns:
        meshtastic.stream_interface.StreamInterface: An instance of StreamInterface
    """
    while True:
        try:
            if system_config['interface_type'] == 'serial':
                if system_config['port']:
                    return meshtastic.serial_interface.SerialInterface(system_config['port'])
                else:
                    ports = list(serial.tools.list_ports.comports())
                    if len(ports) == 1:
                        return meshtastic.serial_interface.SerialInterface(ports[0].device)
                    elif len(ports) > 1:
                        port_list = ', '.join([p.device for p in ports])
                        raise ValueError(f"Multiple serial ports detected: {port_list}. Specify one with the 'port' argument.")
                    else:
                        raise ValueError("No serial ports detected.")
            elif system_config['interface_type'] == 'tcp':
                if not system_config['hostname']:
                    raise ValueError("Hostname must be specified for TCP interface")
                return meshtastic.tcp_interface.TCPInterface(hostname=system_config['hostname'])
            else:
                raise ValueError("Invalid interface type specified in config file")
        except PermissionError as e:
            print(f"PermissionError: {e}. Retrying in 5 seconds...")
            time.sleep(5)
