from rsmesh_bbs import db_operations
from rsmesh_bbs.core_services import (
    CORE_BULLETINS_KEY,
    CORE_CHANNELS_KEY,
    CORE_MAIL_KEY,
    ensure_core_services_config,
    is_core_bulletins_enabled,
    is_core_mail_enabled,
    set_core_service_enabled,
)
from rsmesh_bbs import mesh_ui


def _seed_core_services():
    ensure_core_services_config()


class TestCoreServicesConfig:
    def test_defaults_enabled_when_missing(self, temp_db):
        _seed_core_services()
        assert is_core_bulletins_enabled()
        assert is_core_mail_enabled()
        assert db_operations.get_sys_config_value("bbs", CORE_BULLETINS_KEY) == "true"

    def test_upgrade_adds_missing_yaml_keys(self, temp_db, monkeypatch, tmp_path):
        config_path = tmp_path / "config.yml"
        config_path.write_text("bbs:\n  board_name: Test\n", encoding="utf-8")
        monkeypatch.setattr("rsmesh_bbs.core_services.DEFAULT_CONFIG_FILE", str(config_path))
        _seed_core_services()

        text = config_path.read_text(encoding="utf-8")
        assert "core_bulletins" in text
        assert "core_mail" in text
        assert "core_channels" in text

    def test_disabled_mail_hides_mail_key_on_main_menu(self, temp_db):
        _seed_core_services()
        set_core_service_enabled(CORE_MAIL_KEY, False)
        body = mesh_ui.MAIN_MENU_FILE.read_text(encoding="utf-8")
        assert "[M]ail" not in body
        assert "[B]ulletins" in body
        assert "M[o]dules" in body


class TestMainMenuBody:
    def test_build_main_menu_body_all_enabled(self, temp_db):
        _seed_core_services()
        body = mesh_ui.build_main_menu_body()
        assert "[B]ulletins" in body
        assert "[M]ail" in body
        assert "[C]hannels" in body
        assert "M[o]dules" in body
        assert "[R]ead Mail" not in body

    def test_load_main_menu_body_reads_cached_file(self, temp_db):
        _seed_core_services()
        mesh_ui.MAIN_MENU_FILE.write_text("CUSTOM MENU\n", encoding="utf-8")
        assert mesh_ui.load_main_menu_body() == "CUSTOM MENU\n"


class TestMeshClientCoreServices:
    def test_disabled_bulletins_skips_core_handler(self, mesh_client, temp_db):
        _seed_core_services()
        set_core_service_enabled(CORE_BULLETINS_KEY, False)
        replies = mesh_client.send("b")
        joined = "\n".join(replies)
        assert is_core_bulletins_enabled() is False
        assert "Bulletins are not available." not in joined
        assert "[G]eneral" not in joined
        menu = mesh_client.send_joined("?")
        assert "[B]ulletins" in menu

    def test_disabled_bulletins_routes_to_module(self, mesh_client, temp_db):
        conn = db_operations.get_db_connection()
        conn.execute(
            "UPDATE modules SET enabled = 'Y', menu_option = 'B' WHERE module_dir = 'example_hello'"
        )
        conn.commit()
        mesh_client.interface.module_manager.load_modules(mesh_client.interface)

        _seed_core_services()
        set_core_service_enabled(CORE_BULLETINS_KEY, False)
        replies = mesh_client.send_joined("b")
        assert "Example Hello" in replies
        assert "[G]eneral" not in replies

    def test_disabled_channels_skips_core_handler(self, mesh_client, temp_db):
        _seed_core_services()
        set_core_service_enabled(CORE_CHANNELS_KEY, False)
        replies = mesh_client.send("c")
        joined = "\n".join(replies)
        assert "Channels are not available." not in joined
        assert "Select channel number" not in joined

    def test_disabled_mail_hides_mail_submenu(self, mesh_client, temp_db):
        _seed_core_services()
        set_core_service_enabled(CORE_MAIL_KEY, False)
        replies = mesh_client.send("m")
        joined = "\n".join(replies)
        assert "[R]ead Mail" not in joined
        menu = mesh_client.send_joined("?")
        assert "[M]ail" not in menu
