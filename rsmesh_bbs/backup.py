import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from .module_loader import APP_ROOT, MODULES_DIR
from .sqlite_config import configure_sqlite_connection

BACKUP_DIR = APP_ROOT / "backup"
BACKUP_STAGING_DIR = BACKUP_DIR / "staging"


def _collect_config_files():
    files = []

    for path in sorted(APP_ROOT.glob("config.yml")):
        if path.is_file():
            files.append(path)

    if MODULES_DIR.is_dir():
        for module_dir in sorted(MODULES_DIR.iterdir()):
            if not module_dir.is_dir():
                continue
            config_path = module_dir / "config.yml"
            if config_path.is_file():
                files.append(config_path)

    return files


def _collect_database_files():
    files = []

    for path in sorted(APP_ROOT.glob("*.db")):
        if path.is_file():
            files.append(path)

    if MODULES_DIR.is_dir():
        for module_dir in sorted(MODULES_DIR.iterdir()):
            if not module_dir.is_dir():
                continue
            for db_path in sorted(module_dir.glob("*.db")):
                if db_path.is_file():
                    files.append(db_path)

    return files


def _dump_database(db_path, sql_path):
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    configure_sqlite_connection(conn, read_only=True)
    try:
        with sql_path.open("w", encoding="utf-8", newline="\n") as handle:
            for line in conn.iterdump():
                handle.write(f"{line}\n")
    finally:
        conn.close()


def _clear_staging_dir():
    if BACKUP_STAGING_DIR.exists():
        shutil.rmtree(BACKUP_STAGING_DIR)


def create_application_backup():
    """Dump SQLite databases to SQL under backup/staging, zip, then remove staging dumps."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    archive_path = BACKUP_DIR / f"backup_{timestamp}.zip"
    config_files = _collect_config_files()
    database_files = _collect_database_files()

    BACKUP_DIR.mkdir(exist_ok=True)
    _clear_staging_dir()
    BACKUP_STAGING_DIR.mkdir(parents=True)

    archive_entries = []
    try:
        for db_path in database_files:
            relative_sql = db_path.with_suffix(".sql").relative_to(APP_ROOT)
            sql_path = BACKUP_STAGING_DIR / relative_sql
            _dump_database(db_path, sql_path)
            archive_entries.append((sql_path, relative_sql))

        for config_path in config_files:
            relative_config = config_path.relative_to(APP_ROOT)
            archive_entries.append((config_path, relative_config))

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source_path, archive_name in archive_entries:
                archive.write(source_path, archive_name.as_posix())
    finally:
        _clear_staging_dir()

    return archive_path, len(archive_entries), len(database_files), len(config_files)
