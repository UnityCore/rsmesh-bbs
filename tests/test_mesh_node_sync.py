from rsmesh_bbs import db_operations


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

    def test_ingest_keeps_newer_local_last_heard(self, temp_db):
        db_operations.upsert_mesh_node("!node1", "SN1", "Long", 2000)
        db_operations.ingest_mesh_node_sync(
            "!node1", "SN1", "Long", 1000, sender_node_id="!peer_a",
        )

        row = db_operations.get_mesh_node("!node1")
        assert row[3] == 2000
