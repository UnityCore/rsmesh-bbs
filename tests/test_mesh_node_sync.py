from rsmesh_bbs import db_operations
from rsmesh_bbs.message_processing import _process_sync_message
from rsmesh_bbs.mock_interface import MockMeshInterface
from rsmesh_bbs.sync_wire import encode_nodes_sync_message


def _mark_synced(node_id, peer_id):
    db_operations._mark_mesh_node_synced_to_peer(node_id, peer_id)


def _peer_id(bbs_node):
    return db_operations._peer_id_for_bbs_node(bbs_node)


class TestMeshNodeSync:
    def test_ingest_marks_synced_to_sender(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", sync_mesh_nodes="Y")
        peer_id = _peer_id("!peer_a")

        db_operations.ingest_mesh_node_sync(
            "!node1", "SN1", "Long Name", 1700000000, sender_node_id="!peer_a",
        )

        assert db_operations._mesh_node_synced_to_peer("!node1", peer_id)

    def test_ingest_does_not_invalidate_existing_peer_sync(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", sync_mesh_nodes="Y")
        db_operations.add_sync_peer("!peer_b", sync_protocol="rsv1", sync_mesh_nodes="Y")
        peer_b = _peer_id("!peer_b")

        db_operations.upsert_mesh_node("!node1", "SN1", "Long", 1700000000)
        _mark_synced("!node1", peer_b)

        db_operations.ingest_mesh_node_sync(
            "!node1", "SN1", "Long", 1700000000, sender_node_id="!peer_a",
        )

        assert db_operations._mesh_node_synced_to_peer("!node1", peer_b)
        assert db_operations._mesh_node_synced_to_peer("!node1", _peer_id("!peer_a"))

    def test_unchanged_local_upsert_does_not_invalidate_sync(self, temp_db):
        db_operations.add_sync_peer("!peer_b", sync_protocol="rsv1", sync_mesh_nodes="Y")
        peer_b = _peer_id("!peer_b")

        db_operations.upsert_mesh_node("!node1", "SN1", "Long", 1700000000)
        _mark_synced("!node1", peer_b)
        db_operations.upsert_mesh_node("!node1", "SN1", "Long", 1700000000)

        assert db_operations._mesh_node_synced_to_peer("!node1", peer_b)

    def test_changed_local_last_heard_invalidates_sync(self, temp_db):
        db_operations.add_sync_peer("!peer_b", sync_protocol="rsv1", sync_mesh_nodes="Y")
        peer_b = _peer_id("!peer_b")

        db_operations.upsert_mesh_node("!node1", "SN1", "Long", 1700000000)
        _mark_synced("!node1", peer_b)
        db_operations.upsert_mesh_node("!node1", "SN1", "Long", 1700000100)

        assert not db_operations._mesh_node_synced_to_peer("!node1", peer_b)

    def test_batch_sync_marks_nodes_synced_to_peer(self, temp_db, monkeypatch):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", sync_mesh_nodes="Y")
        db_operations.upsert_mesh_node("!node1", "SN1", "Long1", 1700000000)
        db_operations.upsert_mesh_node("!node2", "SN2", "Long2", 1700000001)
        interface = MockMeshInterface()
        db_operations.reload_sync_peers(interface)
        sent_batches = []

        def _fake_send(batch, peer, iface):
            sent_batches.append(len(batch))
            return True

        monkeypatch.setattr("rsmesh_bbs.utils.send_mesh_nodes_batch_to_peer", _fake_send)

        db_operations.sync_mesh_nodes_to_peers(interface.sync_peers, interface)

        assert sent_batches
        assert sum(sent_batches) == 2
        peer_id = _peer_id("!peer_a")
        assert db_operations._mesh_node_synced_to_peer("!node1", peer_id)
        assert db_operations._mesh_node_synced_to_peer("!node2", peer_id)

    def test_inbound_nodes_sync_ingests_all_entries(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="rsv1", sync_mesh_nodes="Y")
        interface = MockMeshInterface()
        db_operations.reload_sync_peers(interface)
        nodes = [
            ("!node1", "SN1", "Long1", 1700000000),
            ("!node2", "SN2", "Long2", 1700000001),
        ]
        message = encode_nodes_sync_message("rsv1", nodes)
        _process_sync_message(0, message, interface, "!peer_a")

        assert db_operations.get_mesh_node("!node1") is not None
        assert db_operations.get_mesh_node("!node2") is not None

    def test_ingest_keeps_newer_local_last_heard(self, temp_db):
        db_operations.upsert_mesh_node("!node1", "SN1", "Long", 2000)
        db_operations.ingest_mesh_node_sync(
            "!node1", "SN1", "Long", 1000, sender_node_id="!peer_a",
        )

        row = db_operations.get_mesh_node("!node1")
        assert row[3] == 2000
