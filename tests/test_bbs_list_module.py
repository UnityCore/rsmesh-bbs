import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from bbs_list import module as bbs_list_module
from bbs_list import storage
from rsmesh_bbs import db_operations
from rsmesh_bbs.message_processing import _process_rs_sync_message
from rsmesh_bbs.mock_interface import MockMeshInterface
from rsmesh_bbs.module_loader import ModuleManager
from rsmesh_bbs.module_sync import (
    ModuleSyncRegistration,
    get_pending_sync_peers,
    mark_sync_peers_synced,
)
from rsmesh_bbs.sync_wire import build_rs_message


@pytest.fixture
def bbs_list_db(temp_db, monkeypatch, tmp_path):
    db_path = tmp_path / "bbs_list.db"
    monkeypatch.setattr(storage, "DB_PATH", str(db_path))
    storage.setup_db()
    yield db_path


class TestBbsListStorage:
    def test_upsert_and_list_entries(self, bbs_list_db):
        storage.upsert_entry(
            "Alpha BBS",
            "!aabbcc01",
            "ALPH",
            location="Denver, CO",
            sync_interest="Y",
            is_local="Y",
        )
        storage.upsert_entry(
            "Beta BBS",
            "!aabbcc02",
            "BETA",
            sync_interest="N",
        )

        assert len(storage.list_entries()) == 2
        sync_rows = storage.list_entries(sync_only=True)
        assert len(sync_rows) == 1
        assert sync_rows[0]["board_name"] == "Alpha BBS"

    def test_format_list_line(self, bbs_list_db):
        local_entry = {
            "short_name": "RSNA",
            "board_name": "RSMesh BBS",
            "node_hex": "!9e9d8704",
            "location": "Waynedale/Fort Wayne",
            "sync_interest": "Y",
            "is_local": "Y",
        }
        remote_entry = {
            "short_name": "RMT1",
            "board_name": "Remote BBS",
            "node_hex": "!remote01",
            "location": "",
            "sync_interest": "N",
            "is_local": "N",
        }
        assert storage.format_list_line(local_entry) == (
            "RSNA  RSMesh BBS  !9e9d8704  Waynedale/Fort Wayne  sync=Y  LocalPost"
        )
        assert storage.format_list_line(remote_entry) == (
            "RMT1  Remote BBS  !remote01  -  sync=N  RemotePost"
        )

    def test_wire_roundtrip(self, bbs_list_db):
        storage.upsert_entry(
            "Wire BBS",
            "!deadbeef",
            "WIRE",
            location="Test",
            sync_interest="Y",
            is_local="Y",
        )
        entry = storage.get_entry("!deadbeef")
        wire = storage.entry_to_wire(entry)
        assert wire == {
            "uid": "!deadbeef",
            "bn": "Wire BBS",
            "sn": "WIRE",
            "loc": "Test",
            "si": "Y",
        }

        storage.delete_entry("!deadbeef")
        storage.upsert_from_wire(wire)
        restored = storage.get_entry("!deadbeef")
        assert restored["board_name"] == "Wire BBS"
        assert restored["sync_interest"] == "Y"
        assert restored["is_local"] == "N"


class TestBbsListSync:
    def _register(self, manager):
        manager.register_sync(
            4,
            ModuleSyncRegistration(
                module_id=4,
                record_type=storage.RECORD_TYPE,
                wire_suffixes=(storage.WIRE_SUFFIX,),
                on_inbound_rs=bbs_list_module.Module()._ingest_bbs_list_rs,
                sync_pending=bbs_list_module.Module()._sync_pending_bbs_list,
                list_unsynced=storage.list_unsynced_items,
            ),
        )

    def test_outbound_sync_marks_peers_synced(self, temp_db, bbs_list_db, monkeypatch):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", bbs_name="Peer A")
        storage.upsert_entry("Local BBS", "!local0001", "LOC1", sync_interest="Y", is_local="Y")
        bbs_list_module.queue_entry_sync("!local0001")

        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        self._register(interface.module_manager)
        db_operations.reload_sync_peers(interface)

        sent = []

        def _fake_send(message, bbs_node, iface, protocol):
            sent.append((bbs_node, message))
            return True

        monkeypatch.setattr("bbs_list.module.send_sync_message", _fake_send)

        bbs_list_module.Module()._sync_pending_bbs_list(interface.sync_peers, interface)

        assert len(sent) == 1
        assert "BBS_LIST_SYNC" in sent[0][1]
        pending = get_pending_sync_peers(
            storage.RECORD_TYPE,
            "!local0001",
            interface.sync_peers,
            interface,
        )
        assert pending == []

    def test_inbound_sync_accepts_current_wire_type(self, temp_db, bbs_list_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        self._register(interface.module_manager)
        db_operations.reload_sync_peers(interface)

        payload = {
            "uid": "!remote02",
            "bn": "Current Wire BBS",
            "sn": "CUR1",
            "loc": "",
            "si": "N",
        }
        message = build_rs_message(1, storage.wire_type(), payload)
        _process_rs_sync_message(0, message, interface, "!peer_a")

        entry = storage.get_entry("!remote02")
        assert entry is not None
        assert entry["board_name"] == "Current Wire BBS"

    def test_inbound_sync_upserts_entry(self, temp_db, bbs_list_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        self._register(interface.module_manager)
        db_operations.reload_sync_peers(interface)

        payload = {
            "uid": "!remote01",
            "bn": "Remote BBS",
            "sn": "RMT1",
            "loc": "Elsewhere",
            "si": "Y",
        }
        message = build_rs_message(1, storage.wire_type(), payload)
        _process_rs_sync_message(0, message, interface, "!peer_a")

        entry = storage.get_entry("!remote01")
        assert entry is not None
        assert entry["board_name"] == "Remote BBS"
        assert entry["sync_interest"] == "Y"
        assert entry["is_local"] == "N"
