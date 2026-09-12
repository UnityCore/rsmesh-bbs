"""Upgrade installed RSMesh-BBS deployments between release versions."""

import logging

from .config_init import (
    DATABASE_VERSION_KEY,
    DATABASE_VERSION_SECTION,
    DEFAULT_CONFIG_FILE,
    ensure_config_yaml_schema,
)
from .version import VERSION

RELEASE_1_0 = "1.0"
RELEASE_1_1 = "1.1"

RELEASE_ORDER = (RELEASE_1_0, RELEASE_1_1)

_pending_finalize = False


def prepare_release_upgrade(config_file=None):
    """Run pre-database release upgrade steps (for example config.yml merges)."""
    config_file = config_file or DEFAULT_CONFIG_FILE
    migrated = False
    if ensure_config_yaml_schema(config_file):
        logging.info("Merged new release keys into %s.", config_file)
        migrated = True
    return migrated


def migrate_release_database(c):
    """Apply release database migrations and stamp the installed database version."""
    global _pending_finalize

    stored = get_stored_database_version(c)
    if stored == VERSION:
        return False

    migrated = False
    if _needs_1_0_to_1_1_migration(c, stored):
        _migrate_1_0_to_1_1_database(c)
        _pending_finalize = True
        migrated = True

    if stored != VERSION:
        set_stored_database_version(c, VERSION)
        migrated = True

    return migrated


def finalize_release_upgrade(quiet=False):
    """Run post-config steps after sys_config has been seeded (for example main menu)."""
    global _pending_finalize
    if not _pending_finalize:
        return False

    from .mesh_ui import request_main_menu_regeneration

    request_main_menu_regeneration()
    _pending_finalize = False
    message = f"RSMesh-BBS database upgraded to release {VERSION}."
    if quiet:
        logging.info(message)
    else:
        print(message)
    return True


def get_stored_database_version(c):
    if not _table_exists(c, "sys_config"):
        return None
    row = c.execute(
        "SELECT cfg_value FROM sys_config WHERE cfg_section = ? AND cfg_key = ?",
        (DATABASE_VERSION_SECTION, DATABASE_VERSION_KEY),
    ).fetchone()
    return row[0] if row else None


def set_stored_database_version(c, version):
    row = c.execute(
        "SELECT 1 FROM sys_config WHERE cfg_section = ? AND cfg_key = ?",
        (DATABASE_VERSION_SECTION, DATABASE_VERSION_KEY),
    ).fetchone()
    if row:
        c.execute(
            "UPDATE sys_config SET cfg_value = ? WHERE cfg_section = ? AND cfg_key = ?",
            (version, DATABASE_VERSION_SECTION, DATABASE_VERSION_KEY),
        )
    else:
        c.execute(
            "INSERT INTO sys_config (cfg_section, cfg_key, cfg_value) VALUES (?, ?, ?)",
            (DATABASE_VERSION_SECTION, DATABASE_VERSION_KEY, version),
        )


def ensure_release_1_1_schema(c):
    """Idempotent 1.1 schema completion (shared by TC2 and 1.0 upgrade paths)."""
    from .tc2_migration import ensure_tc2_upgrade_schema

    ensure_tc2_upgrade_schema(c)


def _needs_1_0_to_1_1_migration(c, stored_version):
    if stored_version == RELEASE_1_1:
        return False
    if stored_version == RELEASE_1_0:
        return True
    if stored_version is not None:
        return _release_index(stored_version) < _release_index(RELEASE_1_1)
    return _database_has_legacy_content(c)


def _migrate_1_0_to_1_1_database(c):
    stored = get_stored_database_version(c)
    if stored == RELEASE_1_0:
        logging.info(
            "Upgrading RSMesh-BBS database from release %s to %s.",
            RELEASE_1_0,
            RELEASE_1_1,
        )
    else:
        logging.info("Completing RSMesh-BBS database schema for release %s.", RELEASE_1_1)
    ensure_release_1_1_schema(c)
    return True


def _database_has_legacy_content(c):
    """True when upgrading an existing deployment, not a fresh empty install."""
    if not _table_exists(c, "bulletins"):
        return False

    checks = (
        "SELECT 1 FROM bulletins LIMIT 1",
        "SELECT 1 FROM mail LIMIT 1",
        "SELECT 1 FROM sync_peers LIMIT 1",
        "SELECT 1 FROM sysadmin_nodes LIMIT 1",
        "SELECT 1 FROM node_catalog LIMIT 1",
        "SELECT 1 FROM channels LIMIT 1",
    )
    for query in checks:
        try:
            if c.execute(query).fetchone():
                return True
        except Exception:
            continue
    return False


def _release_index(version):
    try:
        return RELEASE_ORDER.index(version)
    except ValueError:
        return -1


def _table_exists(c, name):
    return (
        c.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,),
        ).fetchone()
        is not None
    )
