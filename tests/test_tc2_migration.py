import yaml

from rsmesh_bbs import db_operations
from rsmesh_bbs.tc2_migration import (
    ensure_tc2_upgrade_schema,
    import_tc2_sync_peers_from_ini,
    migrate_tc2_ini_to_yaml,
)


def _create_tc2_mail_table(conn):
    conn.execute("DROP TABLE IF EXISTS mail")
    conn.execute(
        """CREATE TABLE mail (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               sender TEXT NOT NULL,
               sender_short_name TEXT NOT NULL,
               recipient TEXT NOT NULL,
               date TEXT NOT NULL,
               subject TEXT NOT NULL,
               content TEXT NOT NULL,
               unique_id TEXT NOT NULL,
               synced TEXT NOT NULL DEFAULT 'Y',
               read TEXT NOT NULL DEFAULT 'N'
           )"""
    )
    conn.commit()


def _mail_columns(conn):
    return [
        row[1]
        for row in conn.execute("PRAGMA table_info(mail)").fetchall()
    ]


class TestTc2UpgradeSchema:
    def test_adds_main_menu_visible_to_modules(self, temp_db):
        conn = db_operations.get_db_connection()
        conn.execute("DROP TABLE IF EXISTS modules")
        conn.execute(
            """CREATE TABLE modules (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   module_name TEXT NOT NULL,
                   module_dir TEXT NOT NULL UNIQUE,
                   menu_option TEXT NOT NULL UNIQUE COLLATE NOCASE,
                   enabled TEXT NOT NULL DEFAULT 'Y',
                   schedule_enabled TEXT NOT NULL DEFAULT 'N'
               )"""
        )
        conn.commit()
        c = conn.cursor()
        ensure_tc2_upgrade_schema(c)
        conn.commit()

        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(modules)").fetchall()
        ]
        assert "main_menu_visible" in columns

    def test_adds_recipient_short_name_to_legacy_mail(self, temp_db):
        conn = db_operations.get_db_connection()
        _create_tc2_mail_table(conn)
        c = conn.cursor()

        ensure_tc2_upgrade_schema(c)
        conn.commit()

        columns = _mail_columns(conn)
        assert "recipient_short_name" in columns
        assert "recipient" in columns

    def test_initialize_database_succeeds_after_partial_tc2_migration(self, temp_db):
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS bulletins (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   board TEXT NOT NULL,
                   sender_short_name TEXT NOT NULL,
                   date TEXT NOT NULL,
                   subject TEXT NOT NULL,
                   content TEXT NOT NULL,
                   unique_id TEXT NOT NULL,
                   deleted TEXT NOT NULL DEFAULT 'N',
                   delete_reconcile TEXT NOT NULL DEFAULT 'N',
                   synced TEXT NOT NULL DEFAULT 'Y'
               )"""
        )
        _create_tc2_mail_table(conn)

        db_operations.initialize_database(quiet=True)

        assert "recipient_short_name" in _mail_columns(conn)


class TestTc2ConfigImport:
    def test_migrate_tc2_ini_defaults_board_name(self, tmp_path, monkeypatch):
        ini_path = tmp_path / "config.ini"
        yaml_path = tmp_path / "config.yml"
        ini_path.write_text(
            "[interface]\ntype = serial\nport = /dev/ttyUSB0\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        assert migrate_tc2_ini_to_yaml("config.yml") is True
        config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert config["bbs"]["board_name"] == "RSMesh BBS"

    def test_import_tc2_sync_peers_disables_all_sync_flags(self, tmp_path, temp_db):
        ini_path = tmp_path / "config.ini"
        ini_path.write_text(
            "[sync]\nbbs_nodes = !3369e6e4, !aabbccdd\n",
            encoding="utf-8",
        )

        migrated = import_tc2_sync_peers_from_ini(str(ini_path))
        assert migrated == 2

        conn = db_operations.get_db_connection()
        rows = conn.execute(
            "SELECT sync_bulletins, sync_mail, sync_channels, sync_mesh_nodes, "
            "ingest_bulletins, ingest_channels FROM sync_peers ORDER BY bbs_node"
        ).fetchall()
        assert len(rows) == 2
        assert all(row == ("N", "N", "N", "N", "N", "N") for row in rows)

