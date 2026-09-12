"""Follow the BBS server log file from the admin tool."""

import logging
import time
from pathlib import Path

from .config_init import DEFAULT_CONFIG_FILE

DEFAULT_LOG_FILE = "rsmesh-bbs.log"
_LOG_FOLLOW_TAIL_LINES = 100
_LOG_POLL_SECONDS = 0.5
_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_configured_server_log_file() -> str | None:
    from .db_operations import get_sys_config_value

    value = get_sys_config_value("admin", "server_log_file")
    if value and str(value).strip():
        return str(value).strip()
    return None


def config_directory(config_file: str | None = None) -> Path:
    return Path(config_file or DEFAULT_CONFIG_FILE).resolve().parent


def resolve_server_log_path(config_file: str | None = None) -> Path | None:
    """Return the configured log file path, or an existing default log file."""
    configured = get_configured_server_log_file()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = config_directory(config_file) / path
        return path

    default_path = config_directory(config_file) / DEFAULT_LOG_FILE
    if default_path.is_file():
        return default_path
    return None


def server_log_view_available(config_file: str | None = None) -> bool:
    if get_configured_server_log_file():
        return True
    return resolve_server_log_path(config_file) is not None


def attach_server_file_logging(config_file: str | None = None) -> Path | None:
    """Add a file handler when admin.server_log_file is configured."""
    configured = get_configured_server_log_file()
    if not configured:
        return None

    path = Path(configured)
    if not path.is_absolute():
        path = config_directory(config_file) / path
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
    logging.getLogger().addHandler(handler)
    return path


def follow_log_file(path: Path) -> tuple[bool, str | None]:
    if not path.is_file():
        return False, f"Log file not found: {path}"

    print(
        f"Following log file '{path}'. Press Ctrl-C to return to admin.\n",
        flush=True,
    )
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            if size:
                start = max(0, size - 65536)
                handle.seek(start)
                if start:
                    handle.readline()
                tail = handle.readlines()[-_LOG_FOLLOW_TAIL_LINES:]
                for line in tail:
                    print(line, end="", flush=True)

            while True:
                line = handle.readline()
                if line:
                    print(line, end="", flush=True)
                    continue
                time.sleep(_LOG_POLL_SECONDS)
    except KeyboardInterrupt:
        return True, None
    except OSError as exc:
        return False, f"Unable to read log file: {exc}"


def follow_server_log(config_file: str | None = None) -> tuple[bool, str | None]:
    """Follow the server log file until Ctrl-C."""
    log_path = resolve_server_log_path(config_file)
    if log_path is None:
        return (
            False,
            "No server log file configured. Set admin.server_log_file in config.yml "
            f"(for example {DEFAULT_LOG_FILE}) and restart the server.",
        )
    return follow_log_file(log_path)
