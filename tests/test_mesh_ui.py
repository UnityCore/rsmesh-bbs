from rsmesh_bbs import db_operations
from rsmesh_bbs import mesh_ui
from rsmesh_bbs.core_services import (
    CORE_MAIL_KEY,
    ensure_core_services_config,
    set_core_service_enabled,
)


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
        assert mesh_ui.should_show_modules_entry() is False

    def test_hides_modules_when_no_enabled_modules_even_with_suppress_on(self, temp_db):
        _seed()
        self._disable_default_modules()
        mesh_ui.set_suppress_modules_menu(True)
        assert mesh_ui.should_show_modules_entry() is False
        assert "M[o]dules" not in mesh_ui.build_main_menu_body()

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

    def test_suppress_hides_modules_when_all_enabled_on_main_menu(self, temp_db):
        _seed()
        conn = db_operations.get_db_connection()
        conn.execute(
            "UPDATE modules SET main_menu_visible = 'Y' WHERE enabled = 'Y'"
        )
        conn.commit()
        mesh_ui.set_suppress_modules_menu(True)
        body = mesh_ui.build_main_menu_body()
        assert "M[o]dules" not in body

    def test_suppress_ignores_disabled_modules_not_on_main_menu(self, temp_db):
        _seed()
        conn = db_operations.get_db_connection()
        conn.execute(
            "UPDATE modules SET main_menu_visible = 'Y' WHERE enabled = 'Y'"
        )
        conn.execute(
            "UPDATE modules SET enabled = 'N', main_menu_visible = 'N' "
            "WHERE module_dir = 'example_hello'"
        )
        conn.commit()
        mesh_ui.set_suppress_modules_menu(True)
        assert mesh_ui.should_show_modules_entry() is False
        assert "M[o]dules" not in mesh_ui.build_main_menu_body()

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

    def test_validate_rejects_suppress_when_enabled_module_not_on_main_menu(self, temp_db):
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
        ok, message = mesh_ui.validate_enable_suppress_modules_menu()
        assert ok is False
        assert "Node Info" in message

    def test_toggle_suppress_rejects_when_enabled_module_not_on_main_menu(self, temp_db):
        _seed()
        conn = db_operations.get_db_connection()
        conn.execute(
            "UPDATE modules SET enabled = 'Y', main_menu_visible = 'N' "
            "WHERE module_dir = 'node_info'"
        )
        conn.commit()
        ok, message = mesh_ui.toggle_suppress_modules_menu()
        assert ok is False
        assert mesh_ui.is_suppress_modules_menu() is False
        assert "not on the main menu" in message.lower()


class TestDeferredMainMenuRegeneration:
    def test_defers_regeneration_until_context_exits(self, temp_db):
        _seed()
        before = mesh_ui.MAIN_MENU_FILE.read_text(encoding="utf-8")
        with mesh_ui.defer_main_menu_regeneration():
            set_core_service_enabled(CORE_MAIL_KEY, False)
            assert mesh_ui.MAIN_MENU_FILE.read_text(encoding="utf-8") == before
            set_core_service_enabled(CORE_MAIL_KEY, True)
            assert mesh_ui.MAIN_MENU_FILE.read_text(encoding="utf-8") == before
        after = mesh_ui.MAIN_MENU_FILE.read_text(encoding="utf-8")
        assert "[M]ail" in after
        assert mesh_ui.MAIN_MENU_OLD_FILE.read_text(encoding="utf-8") == before

    def test_immediate_regeneration_outside_defer(self, temp_db):
        _seed()
        before = mesh_ui.MAIN_MENU_FILE.read_text(encoding="utf-8")
        set_core_service_enabled(CORE_MAIL_KEY, False)
        after = mesh_ui.MAIN_MENU_FILE.read_text(encoding="utf-8")
        assert after != before
        assert "[M]ail" not in after


class TestModuleMenuOptionValidation:
    def test_reserved_core_keys_rejected_when_service_enabled(self, temp_db):
        _seed()
        ok, message = db_operations.validate_module_menu_option("B")
        assert ok is False
        assert "reserved" in message.lower()

    def test_core_key_available_when_service_disabled(self, temp_db):
        _seed()
        set_core_service_enabled(CORE_MAIL_KEY, False)
        ok, option = db_operations.validate_module_menu_option("M")
        assert ok is True
        assert option == "M"

    def test_mail_submenu_keys_allowed_for_modules(self, temp_db):
        _seed()
        ok, option = db_operations.validate_module_menu_option("R")
        assert ok is True
        assert option == "R"

    def test_mail_main_menu_key_rejected_when_mail_enabled(self, temp_db):
        _seed()
        ok, _message = db_operations.validate_module_menu_option("M")
        assert ok is False

    def test_valid_module_key_accepted(self):
        ok, option = db_operations.validate_module_menu_option("f")
        assert ok is True
        assert option == "F"
