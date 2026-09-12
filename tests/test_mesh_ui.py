from rsmesh_bbs import db_operations
from rsmesh_bbs import mesh_ui
from rsmesh_bbs.core_services import ensure_core_services_config


def _seed():
    ensure_core_services_config()


class TestMainMenuValidation:
    def test_load_main_menu_body_rejects_oversized_cache(self, temp_db):
        _seed()
        mesh_ui.MAIN_MENU_FILE.write_text("X" * 300 + "\n", encoding="utf-8")
        body = mesh_ui.load_main_menu_body()
        assert body == mesh_ui.build_main_menu_body()

    def test_load_main_menu_body_reads_valid_cache(self, temp_db):
        _seed()
        mesh_ui.MAIN_MENU_FILE.write_text("CUSTOM MENU\n", encoding="utf-8")
        assert mesh_ui.load_main_menu_body() == "CUSTOM MENU\n"


class TestMainMenuModules:
    def _disable_default_modules(self):
        conn = db_operations.get_db_connection()
        conn.execute("UPDATE modules SET enabled = 'N'")
        conn.commit()
        mesh_ui.regenerate_main_menu_file()

    def test_hides_modules_when_no_enabled_modules(self, temp_db):
        _seed()
        self._disable_default_modules()
        body = mesh_ui.build_main_menu_body()
        assert "M[o]dules" not in body

    def test_main_menu_visible_adds_module_key(self, temp_db, mesh_client):
        _seed()
        conn = db_operations.get_db_connection()
        conn.execute(
            "UPDATE modules SET enabled = 'Y', main_menu_visible = 'Y' "
            "WHERE module_dir = 'fortune'"
        )
        conn.commit()
        mesh_client.interface.module_manager.load_modules(mesh_client.interface)
        mesh_ui.regenerate_main_menu_file()

        body = mesh_ui.build_main_menu_body()
        assert "[F]ortune" in body
        assert "F" in mesh_ui.get_main_menu_keys()

        replies = mesh_client.send("f")
        assert any("??" in reply or "= Fortune =" in reply for reply in replies)

    def test_suppress_hides_modules_when_all_on_main_menu(self, temp_db):
        _seed()
        conn = db_operations.get_db_connection()
        conn.execute("UPDATE modules SET enabled = 'Y', main_menu_visible = 'Y'")
        conn.commit()
        mesh_ui.set_suppress_modules_menu(True)
        body = mesh_ui.build_main_menu_body()
        assert "M[o]dules" not in body

    def test_suppress_keeps_modules_when_submenu_needed(self, temp_db):
        _seed()
        conn = db_operations.get_db_connection()
        conn.execute(
            "UPDATE modules SET enabled = 'Y', main_menu_visible = 'Y' "
            "WHERE module_dir = 'fortune'"
        )
        conn.execute(
            "UPDATE modules SET enabled = 'Y', main_menu_visible = 'N' "
            "WHERE module_dir = 'node_info'"
        )
        conn.commit()
        mesh_ui.set_suppress_modules_menu(True)
        assert mesh_ui.should_show_modules_entry() is True
        assert "M[o]dules" in mesh_ui.build_main_menu_body()


class TestModuleMenuOptionValidation:
    def test_reserved_core_keys_rejected(self):
        ok, message = db_operations.validate_module_menu_option("B")
        assert ok is False
        assert "reserved" in message.lower()

    def test_mail_submenu_keys_rejected(self):
        ok, _message = db_operations.validate_module_menu_option("R")
        assert ok is False

    def test_valid_module_key_accepted(self):
        ok, option = db_operations.validate_module_menu_option("f")
        assert ok is True
        assert option == "F"
