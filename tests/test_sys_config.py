from rsmesh_bbs import db_operations
from rsmesh_bbs.config_init import (
    build_ordered_config_from_entries,
    get_sys_config_admin_schema,
    get_sys_config_schema,
    load_example_config_defaults,
)


def _seed_sys_config():
    db_operations.ensure_sys_config_from_yaml()


class TestSysConfigSchema:
    def test_example_config_defines_required_sections(self):
        schema = get_sys_config_schema()
        assert list(schema.keys()) == ["bbs", "interface", "schedule"]
        assert "board_name" in schema["bbs"]
        assert "peer_sync_minutes" in schema["schedule"]

    def test_admin_schema_hides_core_service_keys(self):
        admin_schema = get_sys_config_admin_schema()
        assert "core_bulletins" not in admin_schema["bbs"]
        assert "mail_commands_on_main_menu" not in admin_schema["bbs"]
        assert "database_version" not in admin_schema["bbs"]
        assert "board_name" in admin_schema["bbs"]
        assert "node_id" in admin_schema["interface"]
        assert "short_name" in admin_schema["interface"]
        assert "long_name" in admin_schema["interface"]

    def test_database_version_cannot_be_modified_via_sys_config_api(self, temp_db):
        from rsmesh_bbs.release_migration import set_stored_database_version

        conn = db_operations.get_db_connection()
        c = conn.cursor()
        set_stored_database_version(c, "1.1")
        conn.commit()

        assert db_operations.update_sys_config_entry("bbs", "database_version", "9.9") is False
        assert db_operations.delete_sys_config_entry("bbs", "database_version") is False
        assert db_operations.get_sys_config_value("bbs", "database_version") == "1.1"

    def test_ensure_sys_config_seeds_required_keys(self, temp_db):
        _seed_sys_config()
        for cfg_section, cfg_key, _cfg_value in load_example_config_defaults():
            assert db_operations.get_sys_config_value(cfg_section, cfg_key) is not None

    def test_export_orders_keys_by_schema(self, temp_db):
        _seed_sys_config()
        rows = db_operations.get_sys_config_entries()
        config = build_ordered_config_from_entries(rows)
        assert list(config["bbs"].keys())[0] == "board_name"
        assert list(config["schedule"].keys()) == get_sys_config_schema()["schedule"]
