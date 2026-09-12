from rsmesh_bbs import db_operations
from rsmesh_bbs.message_processing import _process_rs_sync_message
from rsmesh_bbs.mock_interface import MockMeshInterface
from rsmesh_bbs.module_loader import ModuleManager
from types import SimpleNamespace

from rsmesh_bbs.module_sync import (
    ModuleSyncRegistration,
    build_module_wire_type,
    count_module_sync_alert_peers,
    format_sync_alerts_summary,
    get_module_sync_status,
    get_module_sync_status_lines,
    get_module_unsynced_records,
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


class TestModuleWireTypes:
    def test_build_module_wire_type_prefixes_module_dir(self):
        assert build_module_wire_type("bbs_list", "sync") == "BBS_LIST_SYNC"
        assert build_module_wire_type("node_info", "delete") == "NODE_INFO_DELETE"


class TestModuleSyncRegistration:
    def test_register_sync_tracks_wire_suffixes(self, temp_db):
        manager = ModuleManager()
        _register_sync(
            manager,
            1,
            record_type="module:node_info",
            wire_suffixes=("EVENT",),
        )

        assert manager.lookup_sync_by_wire_type("NODE_INFO_EVENT") is not None

    def test_register_sync_rejects_record_type_mismatch(self, temp_db):
        manager = ModuleManager()
        _register_sync(
            manager,
            1,
            record_type="module:wrong_dir",
            wire_suffixes=("EVENT",),
        )

        assert manager.lookup_sync_by_wire_type("NODE_INFO_EVENT") is None

    def test_register_sync_rejects_wire_type_collision(self, temp_db):
        manager = ModuleManager()
        _register_sync(
            manager,
            1,
            record_type="module:node_info",
            wire_suffixes=("SYNC",),
        )
        _register_sync(
            manager,
            4,
            record_type="module:bbs_list",
            legacy_wire_types=("NODE_INFO_SYNC",),
            wire_suffixes=("SYNC",),
        )

        node_info_registration = manager.lookup_sync_by_wire_type("NODE_INFO_SYNC")
        bbs_list_registration = manager.lookup_sync_by_wire_type("BBS_LIST_SYNC")
        assert node_info_registration is not None
        assert node_info_registration.module_id == 1
        assert bbs_list_registration is not None
        assert bbs_list_registration.module_id == 4


class TestModuleSyncInbound:
    def test_inbound_rs_calls_handler_when_module_enabled(self, temp_db):
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        _setup_peer(interface)
        received = []
        _register_sync(
            interface.module_manager,
            1,
            record_type="module:node_info",
            wire_suffixes=("EVENT",),
            on_inbound_rs=lambda msg_type, fields, sender, iface: received.append(
                (msg_type, fields, sender)
            ),
        )

        payload = {"uid": "abc123", "body": "hello"}
        message = build_rs_message(1, "NODE_INFO_EVENT", payload)
        _process_rs_sync_message(0, message, interface, "!peer_a")

        assert received == [("NODE_INFO_EVENT", payload, "!peer_a")]

    def test_inbound_rs_skipped_when_module_disabled(self, temp_db):
        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        _setup_peer(interface)
        received = []
        _register_sync(
            interface.module_manager,
            1,
            record_type="module:node_info",
            wire_suffixes=("EVENT",),
            on_inbound_rs=lambda msg_type, fields, sender, iface: received.append(sender),
        )
        db_operations.update_module_flags(1, enabled="N")

        message = build_rs_message(1, "NODE_INFO_EVENT", {"uid": "abc123"})
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
            record_type="module:node_info",
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
            record_type="module:node_info",
            sync_pending=lambda peers, iface: calls.append(True),
        )
        db_operations.update_module_flags(1, enabled="N")

        db_operations.sync_pending_records(interface.sync_peers, interface)

        assert calls == []


class TestModuleSyncListUnsynced:
    def test_get_module_unsynced_records_lists_pending_records(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", bbs_name="Peer A")
        db_operations.add_sync_peer("!peer_b", sync_protocol="rsv1", bbs_name="Peer B")

        manager = ModuleManager()
        interface = SimpleNamespace(module_manager=manager)
        manager.register_sync(
            1,
            ModuleSyncRegistration(
                module_id=1,
                record_type="module:node_info",
                list_unsynced=lambda: [("event-1", "Board meeting")],
            ),
        )

        rows = get_module_unsynced_records(interface)

        assert len(rows) == 1
        assert rows[0][0] == "Node Info"
        assert rows[0][1] == "event-1"
        assert rows[0][2] == "Board meeting"
        assert set(rows[0][3]) == {"Peer A", "Peer B"}

    def test_get_module_unsynced_records_omits_fully_synced(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", bbs_name="Peer A")

        manager = ModuleManager()
        interface = SimpleNamespace(module_manager=manager)
        manager.register_sync(
            1,
            ModuleSyncRegistration(
                module_id=1,
                record_type="module:node_info",
                list_unsynced=lambda: [("event-1", "Board meeting")],
            ),
        )
        mark_sync_peers_synced("module:node_info", "event-1", db_operations.get_sync_peers())

        assert get_module_unsynced_records(interface) == []

    def test_get_unsynced_records_includes_module_rows(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")

        manager = ModuleManager()
        interface = SimpleNamespace(module_manager=manager)
        manager.register_sync(
            1,
            ModuleSyncRegistration(
                module_id=1,
                record_type="module:node_info",
                list_unsynced=lambda: [("event-1", "Board meeting")],
            ),
        )

        _bulletins, _mail, _channels, modules = db_operations.get_unsynced_records(interface)

        assert len(modules) == 1
        assert modules[0][1] == "event-1"


class TestModuleSyncStatusApi:
    def test_format_sync_alerts_summary(self):
        assert format_sync_alerts_summary(0, 0) == (
            "Sync alerts: RS version: 0 peers, Modules: 0 peers"
        )
        assert format_sync_alerts_summary(1, 2) == (
            "Sync alerts: RS version: 1 peer, Modules: 2 peers"
        )

    def test_get_module_sync_status_reports_pending_peers(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", bbs_name="Peer A")
        db_operations.add_sync_peer("!peer_b", sync_protocol="rsv1", bbs_name="Peer B")

        manager = ModuleManager()
        interface = SimpleNamespace(module_manager=manager)
        manager.register_sync(
            1,
            ModuleSyncRegistration(
                module_id=1,
                record_type="module:node_info",
                list_unsynced=lambda: [("event-1", "Board meeting")],
            ),
        )

        status = get_module_sync_status(1, interface)

        assert status is not None
        assert status.pending_record_count == 1
        assert status.pending_peer_count == 2
        assert len(status.records[0].pending_peers) == 2

    def test_count_module_sync_alert_peers_counts_distinct_peers(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        db_operations.add_sync_peer("!peer_b", sync_protocol="rsv1")

        manager = ModuleManager()
        interface = SimpleNamespace(module_manager=manager)
        manager.register_sync(
            1,
            ModuleSyncRegistration(
                module_id=1,
                record_type="module:node_info",
                list_unsynced=lambda: [
                    ("event-1", "One"),
                    ("event-2", "Two"),
                ],
            ),
        )

        assert count_module_sync_alert_peers(interface) == 2

        mark_sync_peers_synced("module:node_info", "event-1", db_operations.get_sync_peers())
        assert count_module_sync_alert_peers(interface) == 2

        mark_sync_peers_synced("module:node_info", "event-2", db_operations.get_sync_peers())
        assert count_module_sync_alert_peers(interface) == 0

    def test_sync_status_lines_uses_custom_formatter(self, temp_db):
        manager = ModuleManager()
        interface = SimpleNamespace(module_manager=manager)
        manager.register_sync(
            1,
            ModuleSyncRegistration(
                module_id=1,
                record_type="module:node_info",
                list_unsynced=lambda: [],
                sync_status_lines=lambda status: [f"Custom: {status.module_name}"],
            ),
        )

        lines = get_module_sync_status_lines(1, interface)
        assert lines == ["Custom: Node Info"]

    def test_system_status_includes_module_sync_alert_peer_count(self, temp_db, monkeypatch):
        monkeypatch.setattr(
            "rsmesh_bbs.module_sync.count_module_sync_alert_peers",
            lambda interface=None: 2,
        )

        status = db_operations.get_system_status()
        assert status["module_sync_alert_peer_count"] == 2


class TestModuleSyncHelpers:
    def test_mark_and_reset_record_sync_peers(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1")
        db_operations.add_sync_peer("!peer_b", sync_protocol="rsv1")
        peers = db_operations.get_sync_peers()
        peer_a = peers[0]

        interface = MockMeshInterface()
        interface.module_manager = ModuleManager()
        _register_sync(
            interface.module_manager,
            1,
            record_type="module:node_info",
        )

        pending = get_pending_sync_peers("module:node_info", "key1", peers, interface)
        assert len(pending) == 2

        mark_sync_peers_synced("module:node_info", "key1", [peer_a])
        pending = get_pending_sync_peers("module:node_info", "key1", peers, interface)
        assert len(pending) == 1

        reset_record_sync_peers("module:node_info", "key1")
        pending = get_pending_sync_peers("module:node_info", "key1", peers, interface)
        assert len(pending) == 2
