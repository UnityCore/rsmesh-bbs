from rsmesh_bbs import db_operations
from rsmesh_bbs.message_processing import _process_rs_sync_message
from rsmesh_bbs.mock_interface import MockMeshInterface
from rsmesh_bbs.module_loader import ModuleManager
from rsmesh_bbs.module_sync import (
    ModuleSyncRegistration,
    get_pending_sync_peers,
)
from rsmesh_bbs.sync_wire import build_rs_message
from rsmesh_bbs.utils import peer_accepts_inbound_sync, peer_sync_enabled


def _register_sync(manager, module_id, **kwargs):
    registration = ModuleSyncRegistration(module_id=module_id, **kwargs)
    manager.register_sync(module_id, registration)
    return registration


class TestSyncPeerModuleFlags:
    def test_defaults_to_allow_when_no_row(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")

        assert db_operations.get_sync_peer_module_flags(peer_id, 1) == ("Y", "Y")

    def test_set_and_read_restricted_flags(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")

        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="N", ingest_in="Y")
        assert db_operations.get_sync_peer_module_flags(peer_id, 1) == ("N", "Y")

        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="Y", ingest_in="N")
        assert db_operations.get_sync_peer_module_flags(peer_id, 1) == ("Y", "N")

    def test_reset_to_defaults_deletes_row(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")

        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="N", ingest_in="Y")
        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="Y", ingest_in="Y")

        assert db_operations.get_sync_peer_module_flags(peer_id, 1) == ("Y", "Y")
        assert db_operations.get_sync_peer_module_flags_for_peer(peer_id) == {}


class TestSyncPeerModuleGating:
    def _setup(self):
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        db_operations.add_sync_peer("!peer_b", sync_protocol="tc2")
        db_operations.reload_sync_peers(interface)
        peer_a = next(row for row in interface.sync_peers if row[1] == "!peer_a")
        peer_b = next(row for row in interface.sync_peers if row[1] == "!peer_b")
        _register_sync(
            interface.module_manager,
            1,
            record_type="module:node_info",
            wire_suffixes=("EVENT",),
            on_inbound_rs=lambda *_args: None,
        )
        return interface, peer_a, peer_b

    def test_sync_out_disabled_excludes_peer_from_pending(self, temp_db):
        interface, peer_a, _peer_b = self._setup()
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")
        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="N", ingest_in="Y")

        pending = get_pending_sync_peers(
            "module:node_info",
            "key1",
            interface.sync_peers,
            interface,
        )

        assert pending == []

    def test_ingest_in_disabled_blocks_inbound_acceptance(self, temp_db):
        interface, peer_a, _peer_b = self._setup()
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")
        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="Y", ingest_in="N")

        assert not peer_accepts_inbound_sync(peer_a, "module:node_info", interface)

    def test_tc2_peer_blocked_for_module_sync(self, temp_db):
        interface, _peer_a, peer_b = self._setup()

        assert not peer_sync_enabled(peer_b, "module:node_info", interface)
        assert not peer_accepts_inbound_sync(peer_b, "module:node_info", interface)

    def test_inbound_rs_skipped_when_ingest_disabled(self, temp_db):
        interface, _peer_a, _peer_b = self._setup()
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")
        db_operations.set_sync_peer_module_flags(peer_id, 1, sync_out="Y", ingest_in="N")
        received = []
        interface.module_manager.get_sync_registrations()[0].on_inbound_rs = (
            lambda *_args: received.append(True)
        )

        message = build_rs_message(1, "NODE_INFO_EVENT", {"uid": "abc123"})
        _process_rs_sync_message(0, message, interface, "!peer_a")

        assert received == []
