import json
import uuid
from unittest.mock import MagicMock

import pytest

from rsmesh_bbs import db_operations
from rsmesh_bbs.sync_wire import encode_bulletin_sync_message, parse_rs_envelope, _decode_rs_payload
from rsmesh_bbs.utils import send_bulletin_to_sync_peers


def _decode_bulletin_fields(message):
    wire_version, msg_type, payload = parse_rs_envelope(message)
    decoded_type, fields = _decode_rs_payload(wire_version, msg_type, payload)
    assert decoded_type == "BULLETIN"
    return fields


def _count_rows(table, where_clause="", params=()):
    conn = db_operations.get_db_connection()
    query = f"SELECT COUNT(*) FROM {table}"
    if where_clause:
        query += f" WHERE {where_clause}"
    return conn.execute(query, params).fetchone()[0]


def _add_rsv1_peer(temp_db, peer_node="!peer_rsv1"):
    db_operations.add_sync_peer(
        peer_node,
        sync_protocol="rsv1",
        bbs_name="RS Peer",
        sync_bulletins="Y",
        sync_mail="N",
        sync_channels="N",
        sync_mesh_nodes="N",
        ingest_bulletins="Y",
        ingest_channels="N",
        enabled="Y",
    )


class TestRsv1BulletinWireFormat:
    def test_encode_includes_pinned_flag(self):
        message = encode_bulletin_sync_message(
            "rsv1", "General", "OPS", "Subject", "Body", "uid-1", pinned="Y"
        )
        fields = _decode_bulletin_fields(message)
        assert fields["pinned"] == "Y"

    def test_decode_defaults_pinned_to_n_when_missing(self):
        payload = json.dumps(
            {"b": "General", "sn": "OPS", "sub": "S", "body": "B", "uid": "uid-2"},
            separators=(",", ":"),
        )
        _, fields = _decode_rs_payload(1, "BULLETIN", payload)
        assert fields["pinned"] == "N"

    def test_tc2_encode_unchanged_without_pinned(self):
        message = encode_bulletin_sync_message(
            "tc2", "General", "OPS", "Subject", "Body", "uid-3", pinned="Y"
        )
        assert message == "BULLETIN|General|OPS|Subject|Body|uid-3"


class TestRsv1BulletinUpsert:
    def test_upsert_updates_existing_bulletin(self, temp_db):
        unique_id = str(uuid.uuid4())
        db_operations.ingest_bulletin_from_rsv1_sync(
            "General", "OPS", "First", "Body one", unique_id, pinned="N", interface=None
        )
        db_operations.ingest_bulletin_from_rsv1_sync(
            "Urgent", "OPS", "Updated", "Body two", unique_id, pinned="Y", interface=None
        )

        conn = db_operations.get_db_connection()
        row = conn.execute(
            "SELECT board, subject, content, pinned FROM bulletins WHERE unique_id = ?",
            (unique_id,),
        ).fetchone()
        assert row == ("Urgent", "Updated", "Body two", "Y")
        assert _count_rows("bulletins", "unique_id = ?", (unique_id,)) == 1

    def test_tc2_duplicate_ingest_still_skipped(self, temp_db):
        unique_id = str(uuid.uuid4())
        db_operations.add_bulletin(
            "General", "OPS", "Subject", "Body", [], None, unique_id=unique_id, from_sync=True
        )
        db_operations.add_bulletin(
            "General", "OPS", "Changed", "New body", [], None, unique_id=unique_id, from_sync=True
        )

        conn = db_operations.get_db_connection()
        row = conn.execute(
            "SELECT subject, content FROM bulletins WHERE unique_id = ?", (unique_id,)
        ).fetchone()
        assert row == ("Subject", "Body")

    def test_deleted_bulletin_skips_rsv1_update(self, temp_db):
        unique_id = str(uuid.uuid4())
        db_operations.add_bulletin(
            "General", "OPS", "Subject", "Body", [], None, unique_id=unique_id
        )
        conn = db_operations.get_db_connection()
        bulletin_id = conn.execute(
            "SELECT id FROM bulletins WHERE unique_id = ?", (unique_id,)
        ).fetchone()[0]
        db_operations.mark_bulletin_deleted(bulletin_id)

        db_operations.ingest_bulletin_from_rsv1_sync(
            "General", "OPS", "Updated", "New body", unique_id, pinned="Y", interface=None
        )
        row = conn.execute(
            "SELECT subject, content, pinned, deleted FROM bulletins WHERE unique_id = ?",
            (unique_id,),
        ).fetchone()
        assert row == ("Subject", "Body", "N", "Y")


class TestRsv1BulletinOutboundSync:
    def test_send_bulletin_includes_pinned_for_rsv1_peer(self, temp_db, monkeypatch):
        _add_rsv1_peer(temp_db)
        unique_id = str(uuid.uuid4())
        conn = db_operations.get_db_connection()
        conn.execute(
            "INSERT INTO bulletins "
            "(board, sender_short_name, date, subject, content, unique_id, synced, pinned) "
            "VALUES (?, ?, ?, ?, ?, ?, 'N', 'Y')",
            ("General", "OPS", "2020-01-01 00:00", "Pinned post", "Body", unique_id),
        )
        conn.commit()

        captured = []

        def _fake_send_sync_message(message, destination, interface, sync_protocol=None):
            captured.append((message, sync_protocol))
            return True

        monkeypatch.setattr("rsmesh_bbs.utils.send_sync_message", _fake_send_sync_message)
        peers = db_operations.get_sync_peers()
        interface = MagicMock(sync_peers=peers)

        send_bulletin_to_sync_peers(
            "General", "OPS", "Pinned post", "Body", unique_id, peers, interface, pinned="Y"
        )

        assert len(captured) == 1
        message, protocol = captured[0]
        assert protocol == "rsv1"
        fields = _decode_bulletin_fields(message)
        assert fields["pinned"] == "Y"
        assert fields["subject"] == "Pinned post"
