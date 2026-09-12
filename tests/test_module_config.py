import pytest

from rsmesh_bbs import db_operations
from rsmesh_bbs.mock_interface import MockMeshInterface
from rsmesh_bbs.module_loader import ModuleManager


class _ConfigModule:
    def on_load(self, ctx):
        ctx.register_config("default_sync_interest", default=False, editor="bool")
        self.ctx = ctx


class TestModuleConfigApi:
    def test_register_and_read_module_config(self, temp_db):
        interface = MockMeshInterface()
        manager = ModuleManager()
        row = db_operations.get_module_by_id(4)
        from rsmesh_bbs.module_loader import ModuleContext

        module = _ConfigModule()
        context = ModuleContext(row, interface=interface, manager=manager)
        module.on_load(context)

        assert context.get_config("default_sync_interest") is False
        assert db_operations.get_sys_config_value("module:bbs_list", "default_sync_interest") == "false"

    def test_get_config_rejects_foreign_section(self, temp_db):
        interface = MockMeshInterface()
        manager = ModuleManager()
        row = db_operations.get_module_by_id(4)
        from rsmesh_bbs.module_loader import ModuleContext

        context = ModuleContext(row, interface=interface, manager=manager)
        db_operations.add_sys_config_entry("module:node_info", "secret", "1")

        with pytest.raises(ValueError):
            context.get_config("../node_info/secret")

    def test_get_config_cannot_read_other_module_keys(self, temp_db):
        interface = MockMeshInterface()
        manager = ModuleManager()
        row = db_operations.get_module_by_id(4)
        from rsmesh_bbs.module_loader import ModuleContext

        context = ModuleContext(row, interface=interface, manager=manager)
        db_operations.add_sys_config_entry("module:node_info", "scan_minutes", "5")

        assert context.get_config("scan_minutes", default=None) is None
