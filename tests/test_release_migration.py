import uuid

import yaml

from rsmesh_bbs import db_operations
from rsmesh_bbs.release_migration import (
    RELEASE_1_0,
    RELEASE_1_1,
    ensure_release_1_1_schema,
    finalize_release_upgrade,
    get_stored_database_version,
    migrate_release_database,
    prepare_release_upgrade,
    set_stored_database_version,
)
from rsmesh_bbs.version import VERSION


class TestReleaseMigration:
    def test_fresh_install_stamps_database_version(self, temp_db):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        assert get_stored_database_version(c) == VERSION

    def test_second_migration_is_noop(self, temp_db):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        assert migrate_release_database(c) is False

    def test_migrates_legacy_database_with_content(self, temp_db):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        c.execute(
            "DELETE FROM sys_config WHERE cfg_section = 'bbs' AND cfg_key = 'database_version'"
        )
        c.execute(
            "INSERT INTO bulletins "
            "(board, sender_short_name, date, subject, content, unique_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("General", "ABCD", "2026-01-01 00:00", "Subject", "Body", str(uuid.uuid4())),
        )
        conn.commit()

        assert migrate_release_database(c) is True
        conn.commit()
        assert get_stored_database_version(c) == RELEASE_1_1

    def test_skips_data_migration_for_empty_legacy_database(self, temp_db):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        c.execute(
            "DELETE FROM sys_config WHERE cfg_section = 'bbs' AND cfg_key = 'database_version'"
        )
        conn.commit()

        assert migrate_release_database(c) is True
        conn.commit()
        assert get_stored_database_version(c) == RELEASE_1_1

    def test_migrates_when_stored_version_is_1_0(self, temp_db):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        set_stored_database_version(c, RELEASE_1_0)
        conn.commit()

        assert migrate_release_database(c) is True
        conn.commit()
        assert get_stored_database_version(c) == RELEASE_1_1

    def test_prepare_release_upgrade_merges_missing_config_keys(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            yaml.dump(
                {
                    "bbs": {"board_name": "Legacy BBS"},
                    "interface": {"type": "serial"},
                    "schedule": {"peer_sync_minutes": 5},
                },
                default_flow_style=False,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        assert prepare_release_upgrade("config.yml") is True
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert config["bbs"]["core_bulletins"] is True
        assert config["bbs"]["mail_commands_on_main_menu"] is False

    def test_migrate_1_0_to_1_1_adds_release_schema(self, temp_db):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        c.execute("DROP TABLE IF EXISTS sync_peer_modules")
        c.execute("DROP TABLE IF EXISTS modules")
        c.execute(
            """CREATE TABLE modules (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   module_name TEXT NOT NULL,
                   module_dir TEXT NOT NULL UNIQUE,
                   menu_option TEXT NOT NULL UNIQUE COLLATE NOCASE,
                   enabled TEXT NOT NULL DEFAULT 'Y',
                   schedule_enabled TEXT NOT NULL DEFAULT 'N'
               )"""
        )
        set_stored_database_version(c, RELEASE_1_0)
        conn.commit()

        assert migrate_release_database(c) is True
        conn.commit()

        module_columns = [
            row[1] for row in c.execute("PRAGMA table_info(modules)").fetchall()
        ]
        assert "main_menu_visible" in module_columns
        assert c.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sync_peer_modules'"
        ).fetchone() is not None
        assert get_stored_database_version(c) == RELEASE_1_1

    def test_ensure_release_1_1_schema_is_idempotent(self, temp_db):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        ensure_release_1_1_schema(c)
        conn.commit()
        module_columns = [
            row[1] for row in c.execute("PRAGMA table_info(modules)").fetchall()
        ]
        assert "main_menu_visible" in module_columns

        ensure_release_1_1_schema(c)
        conn.commit()
        assert module_columns == [
            row[1] for row in c.execute("PRAGMA table_info(modules)").fetchall()
        ]

    def test_finalize_release_upgrade_runs_after_legacy_migration(self, temp_db, monkeypatch):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        set_stored_database_version(c, RELEASE_1_0)
        conn.commit()

        regen = []
        monkeypatch.setattr(
            "rsmesh_bbs.mesh_ui.request_main_menu_regeneration",
            lambda: regen.append(True),
        )

        migrate_release_database(c)
        conn.commit()
        assert finalize_release_upgrade(quiet=True) is True
        assert regen == [1]
        assert finalize_release_upgrade(quiet=True) is False
