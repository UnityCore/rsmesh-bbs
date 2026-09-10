from rsmesh_bbs import db_operations
from rsmesh_bbs.utils import filter_peers_for_record_type, peer_accepts_inbound_sync


class TestSyncPeerEnabled:
    def test_disabled_peer_excluded_from_outbound_sync(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="tc2")
        db_operations.add_sync_peer("!peer_b", sync_protocol="tc2", enabled="N")

        peers = db_operations.get_sync_peers()
        bulletin_peers = filter_peers_for_record_type(peers, "bulletins")

        assert len(bulletin_peers) == 1
        assert bulletin_peers[0][1] == "!peer_a"

    def test_disabled_peer_rejects_inbound_sync(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="tc2", enabled="N")
        peer = db_operations.get_sync_peers()[0]

        assert not peer_accepts_inbound_sync(peer, "bulletins")
        assert not peer_accepts_inbound_sync(peer, "mail")

    def test_disabling_peer_clears_record_sync_state(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="tc2")
        peer_id = db_operations._peer_id_for_bbs_node("!peer_a")
        unique_id = db_operations.add_bulletin(
            "General", "POST", "Subject", "Body", None, None,
        )
        db_operations._mark_peers_synced("bulletins", unique_id, [peer_id])

        assert db_operations._count_synced_peers_for_record("bulletins", unique_id) == 1

        db_operations.update_sync_peer(
            peer_id,
            "!peer_a",
            "tc2",
            enabled="N",
        )

        assert db_operations._count_synced_peers_for_record("bulletins", unique_id) == 0
        assert db_operations.get_sync_status_label("bulletins", unique_id) == "Y"

    def test_enabled_defaults_to_y_for_existing_schema(self, temp_db):
        db_operations.add_sync_peer("!peer_a", sync_protocol="tc2")
        peer = db_operations.get_sync_peers()[0]

        assert peer[13] == "Y"
