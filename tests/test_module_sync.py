from rsmesh_bbs import db_operations
from rsmesh_bbs.message_processing import _process_rs_sync_message
from rsmesh_bbs.mock_interface import MockMeshInterface
from rsmesh_bbs.module_loader import ModuleManager
from rsmesh_bbs.module_sync import (
    ModuleSyncRegistration,
    get_pending_sync_peers,
    mark_sync_peers_synced,
    reset_record_sync_peers,
)
from rsmesh_bbs.sync_wire import build_rs_message


def _setup_peer(interface, peer_node="!peer_a"):
    db_operations.add_sync_peer(peer_node, sync_protocol="rsv1")
    interface.bbs_nodes = [peer_node]
    db_operations.reload_sync_peers(interface)


def _register_sync(manager, module_id, **kwargs):
    registration = ModuleSyncRegistration(module_id=module_id, **kwargs)
    manager.register_sync(module_id, registration)
    return registration


class TestModuleSyncRegistration:
    def test_register_sync_tracks_wire_types(self):
        manager = ModuleManager()
        _register_sync(
            manager,
            1,
            record_type="module:test",
            wire_types=("TestEvent",),
        )

        assert manager.lookup_sync_by_wire_type("TESTEVENT") is not None


class TestModuleSyncInbound:
    def test_inbound_rs_calls_handler_when_module_enabled(self, temp_db):
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        _setup_peer(interface)
        received = []
        _register_sync(
            interface.module_manager,
            1,
            record_type="module:test",
            wire_types=("TESTEVENT",),
            on_inbound_rs=lambda msg_type, fields, sender, iface: received.append(
                (msg_type, fields, sender)
            ),
        )

        payload = {"uid": "abc123", "body": "hello"}
        message = build_rs_message(1, "TESTEVENT", payload)
        _process_rs_sync_message(0, message, interface, "!peer_a")

        assert received == [("TESTEVENT", payload, "!peer_a")]

    def test_inbound_rs_skipped_when_module_disabled(self, temp_db):
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        _setup_peer(interface)
        received = []
        _register_sync(
            interface.module_manager,
            1,
            record_type="module:test",
            wire_types=("TESTEVENT",),
            on_inbound_rs=lambda msg_type, fields, sender, iface: received.append(sender),
        )
        db_operations.update_module_flags(1, enabled="N")

        message = build_rs_message(1, "TESTEVENT", {"uid": "abc123"})
        _process_rs_sync_message(0, message, interface, "!peer_a")

        assert received == []


class TestModuleSyncOutbound:
    def test_sync_pending_records_invokes_module_handler(self, temp_db):
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        _setup_peer(interface)
        calls = []
        _register_sync(
            interface.module_manager,
            1,
            record_type="module:test",
            sync_pending=lambda peers, iface: calls.append(list(peers)),
        )

        db_operations.sync_pending_records(interface.sync_peers, interface)

        assert len(calls) == 1
        assert calls[0][0][1] == "!peer_a"

    def test_sync_pending_skipped_when_module_disabled(self, temp_db):
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        _setup_peer(interface)
        calls = []
        _register_sync(
            interface.module_manager,
            1,
            record_type="module:test",
            sync_pending=lambda peers, iface: calls.append(True),
        )
        db_operations.update_module_flags(1, enabled="N")

        db_operations.sync_pending_records(interface.sync_peers, interface)

        assert calls == []


class TestModuleSyncHelpers:
    def test_mark_and_reset_record_sync_peers(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        db_operations.add_sync_peer("!peer_b", sync_protocol="rsv1")
        peers = db_operations.get_sync_peers()
        peer_a = peers[0]

        pending = get_pending_sync_peers("module:test", "key1", peers)
        assert len(pending) == 2

        mark_sync_peers_synced("module:test", "key1", [peer_a])
        pending = get_pending_sync_peers("module:test", "key1", peers)
        assert len(pending) == 1

        reset_record_sync_peers("module:test", "key1")
        pending = get_pending_sync_peers("module:test", "key1", peers)
        assert len(pending) == 2
