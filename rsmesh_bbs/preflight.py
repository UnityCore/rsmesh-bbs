"""Startup validation with actionable error messages for systemd and CLI."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from .config_init import DEFAULT_CONFIG_FILE
from .version import BBS_DB_FILE


def _fail(message: str, code: int = 1):
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _venv_python_path(project_dir: Path) -> Path | None:
    if sys.platform == "win32":
        candidate = project_dir / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = project_dir / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else None


def run_server_preflight(config_file: str | None = None):
    """Validate install layout before opening the radio interface."""
    project_dir = Path.cwd()
    config_path = Path(config_file or DEFAULT_CONFIG_FILE)
    if not config_path.is_file():
        _fail(
            f"configuration file not found: {config_path.resolve()}. "
            f"Copy example_config.yml to {config_path.name} in {project_dir}."
        )

    venv_python = _venv_python_path(project_dir)
    if venv_python is None:
        _fail(
            f"virtual environment not found under {project_dir / '.venv'}. "
            "Run: python3 -m venv .venv && "
            ".venv/bin/python -m pip install -r requirements.txt"
        )

    try:
        resolved = Path(sys.executable).resolve()
        if resolved != venv_python.resolve():
            _fail(
                f"server must be started with {venv_python}, not {resolved}. "
                "Update the systemd ExecStart path or activate the project venv."
            )
    except OSError:
        pass

    for package in ("meshtastic", "pubsub", "rich", "yaml"):
        try:
            __import__(package)
        except ImportError as exc:
            _fail(
                f"missing Python package '{package}' ({exc}). "
                "Run: .venv/bin/python -m pip install -r requirements.txt"
            )

    _check_database_writable(project_dir)


def _check_database_writable(project_dir: Path):
    if not os.access(project_dir, os.W_OK):
        _fail(
            f"cannot write to install directory {project_dir}. "
            f"Ensure the service user owns the tree (for example: "
            f"sudo chown -R <service-user> {project_dir})."
        )

    db_path = project_dir / BBS_DB_FILE
    for sidecar_suffix in ("", "-wal", "-shm"):
        sidecar = project_dir / f"{BBS_DB_FILE}{sidecar_suffix}"
        if sidecar.exists() and not os.access(sidecar, os.W_OK):
            _fail(
                f"cannot write database file {sidecar}. "
                f"Ensure the service user owns {project_dir} (for example: "
                f"sudo chown -R <service-user> {project_dir})."
            )

    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.close()
    except sqlite3.OperationalError as exc:
        if "readonly" in str(exc).lower():
            _fail(
                f"database {db_path} is read-only for the current user. "
                f"Fix ownership under {project_dir} (for example: "
                f"sudo chown -R <service-user> {project_dir})."
            )
        raise


def os_access_writable(path: Path) -> bool:
    return os.access(path, os.W_OK)
