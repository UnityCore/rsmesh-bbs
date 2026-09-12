import importlib.util
from pathlib import Path

from rsmesh_bbs import db_operations
from rsmesh_bbs.module_loader import ModuleManager
from rsmesh_bbs.module_sync import ModuleSyncRegistration, get_registered_module_sync_rows


def _load_admin_module(monkeypatch):
    script_path = Path(__file__).resolve().parents[1] / "rsmesh-bbs_admin.py"
    spec = importlib.util.spec_from_file_location("rsmesh_bbs_admin", script_path)
    admin_module = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(
        "rsmesh_bbs.venv_guard.require_venv",
        lambda: None,
        raising=False,
    )
    spec.loader.exec_module(admin_module)
    return admin_module


class TestRegisteredModuleSyncRows:
    def test_returns_empty_when_no_modules_register_sync(self, temp_db):
        assert get_registered_module_sync_rows() == []

    def test_returns_registration_for_loaded_module(self, temp_db, monkeypatch):
        manager = ModuleManager()
        manager.register_sync(
            1,
            ModuleSyncRegistration(
                module_id=1,
                record_type="module:test",
                wire_types=("TESTEVENT",),
            ),
        )
        rows = [(reg, db_operations.get_module_by_id(1)) for reg in manager.get_sync_registrations()]
        assert len(rows) == 1
        assert rows[0][1][1] == "Node Info"


class TestSyncPeerModuleAdminPrompt:
    def test_prompt_skips_tc2_protocol(self, temp_db, monkeypatch, capsys):
        admin_module = _load_admin_module(monkeypatch)
        db_operations.add_sync_peer("!peer_a", sync_protocol="tc2")
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")

        admin_module._prompt_sync_peer_module_flags(peer_id, "tc2")

        assert "N/A (rsv1 only)" in capsys.readouterr().out

    def test_prompt_stores_module_flags_for_rsv1_peer(self, temp_db, monkeypatch):
        admin_module = _load_admin_module(monkeypatch)
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")

        manager = ModuleManager()
        manager.register_sync(
            1,
            ModuleSyncRegistration(module_id=1, record_type="module:test"),
        )
        monkeypatch.setattr(
            admin_module,
            "get_registered_module_sync_rows",
            lambda: [(manager.get_sync_registrations()[0], db_operations.get_module_by_id(1))],
        )
        inputs = iter(["N", "Y"])
        monkeypatch.setattr(admin_module, "input_bold", lambda _prompt: next(inputs))

        admin_module._prompt_sync_peer_module_flags(peer_id, "rsv1")

        assert db_operations.get_sync_peer_module_flags(peer_id, 1) == ("N", "Y")


class TestSyncPeerModuleListDisplay:
    def test_restriction_line_omitted_when_all_allowed(self, temp_db, monkeypatch):
        admin_module = _load_admin_module(monkeypatch)
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        peer = db_operations.get_sync_peers()[0]
        module_rows = []

        assert admin_module._sync_peer_module_restriction_line(peer, module_rows) is None

    def test_restriction_line_shows_non_default_flags(self, temp_db, monkeypatch):
        admin_module = _load_admin_module(monkeypatch)
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        peer = db_operations.get_sync_peers()[0]
        peer_id = peer[0]
        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="N", ingest_in="Y")
        module_row = db_operations.get_module_by_id(1)
        module_rows = [
            (
                ModuleSyncRegistration(module_id=1, record_type="module:test"),
                module_row,
            )
        ]

        line = admin_module._sync_peer_module_restriction_line(peer, module_rows)

        assert line is not None
        assert "Node Info out=N" in line
        assert "in=N" not in line

    def test_sync_peer_lines_includes_module_restriction(self, temp_db, monkeypatch):
        admin_module = _load_admin_module(monkeypatch)
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", bbs_name="Peer A")
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")
        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="Y", ingest_in="N")
        module_row = db_operations.get_module_by_id(1)
        monkeypatch.setattr(
            admin_module,
            "get_registered_module_sync_rows",
            lambda: [
                (
                    ModuleSyncRegistration(module_id=1, record_type="module:test"),
                    module_row,
                )
            ],
        )

        lines = admin_module._sync_peer_lines(db_operations.get_sync_peers())

        assert any("Node Info in=N" in line for line in lines)


class TestListUnsyncedModuleDisplay:
    def test_unsynced_lines_includes_modules_section(self, temp_db, monkeypatch):
        admin_module = _load_admin_module(monkeypatch)
        modules = [("Events", "event-1", "Board meeting", ["Peer A", "Peer B"])]

        lines = admin_module._unsynced_lines([], [], [], modules)

        assert any("Modules:" in line for line in lines)
        assert any("Board meeting" in line for line in lines)
        assert any("Peer A" in line for line in lines)
