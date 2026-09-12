import pytest

from rsmesh_bbs.sync_wire import (
    RS_CHUNK_TYPE,
    SYNC_PACKET_MAX_LEN,
    SyncChunkAssembler,
    _decode_rs_payload,
    build_rs_chunk_sequence,
    encode_bulletin_sync_message,
    encode_channel_sync_message,
    encode_delete_bulletin_sync_message,
    encode_delete_channel_sync_message,
    encode_delete_mail_sync_message,
    encode_mail_sync_message,
    dedupe_mesh_node_entries,
    encode_nodes_sync_message,
    plan_nodes_sync_batches,
    is_rs_sync_protocol,
    parse_rs_chunk_payload,
    parse_rs_envelope,
    plan_sync_transmit_packets,
    rs_wire_version_for_protocol,
)


BULLETIN_UID = "550e8400-e29b-41d4-a716-446655440001"
MAIL_UID = "550e8400-e29b-41d4-a716-446655440002"
CHANNEL_UID = "550e8400-e29b-41d4-a716-446655440003"
NODE_ID = "!a1b2c3d4"


def _decode_rs_message(message):
    wire_version, msg_type, payload = parse_rs_envelope(message)
    return wire_version, *_decode_rs_payload(wire_version, msg_type, payload)


def _reassemble_chunks(assembler, sender_node_id, packets):
    complete = None
    for packet in packets:
        wire_version, msg_type, payload = parse_rs_envelope(packet)
        assert msg_type == RS_CHUNK_TYPE
        transfer_id, index, total, chunk_payload = parse_rs_chunk_payload(payload)
        complete = assembler.add_chunk(
            sender_node_id, transfer_id, index, total, chunk_payload
        )
    return complete


class TestProtocolHelpers:
    def test_rs_wire_version_for_protocol(self):
        assert rs_wire_version_for_protocol("rsv1") == 1
        assert rs_wire_version_for_protocol("tc2") is None
        assert rs_wire_version_for_protocol("invalid") is None

    def test_is_rs_sync_protocol(self):
        assert is_rs_sync_protocol("rsv1") is True
        assert is_rs_sync_protocol("tc2") is False


class TestRsEncodeDecodeRoundTrips:
    def test_bulletin_round_trip(self):
        message = encode_bulletin_sync_message(
            "rsv1", "general", "ALICE", "Hello", "Body text", BULLETIN_UID
        )
        msg_type, fields = _decode_rs_message(message)[1:]
        assert msg_type == "BULLETIN"
        assert fields == {
            "board": "general",
            "sender_short_name": "ALICE",
            "subject": "Hello",
            "content": "Body text",
            "unique_id": BULLETIN_UID,
            "pinned": "N",
        }

    def test_bulletin_round_trip_with_pinned(self):
        message = encode_bulletin_sync_message(
            "rsv1", "general", "ALICE", "Hello", "Body text", BULLETIN_UID, pinned="Y"
        )
        msg_type, fields = _decode_rs_message(message)[1:]
        assert msg_type == "BULLETIN"
        assert fields["pinned"] == "Y"

    def test_mail_round_trip(self):
        message = encode_mail_sync_message(
            "rsv1",
            NODE_ID,
            "ALICE",
            NODE_ID,
            "BOB",
            "Mail subject",
            "Mail body",
            MAIL_UID,
        )
        msg_type, fields = _decode_rs_message(message)[1:]
        assert msg_type == "MAIL"
        assert fields["sender_short_name"] == "ALICE"
        assert fields["subject"] == "Mail subject"
        assert fields["content"] == "Mail body"
        assert fields["unique_id"] == MAIL_UID

    def test_channel_round_trip(self):
        message = encode_channel_sync_message("rsv1", "mesh-chat", "psk123", CHANNEL_UID)
        msg_type, fields = _decode_rs_message(message)[1:]
        assert msg_type == "CHANNEL"
        assert fields == {
            "channel_name": "mesh-chat",
            "channel_psk": "psk123",
            "unique_id": CHANNEL_UID,
        }

    def test_delete_messages_round_trip(self):
        bulletin_delete = encode_delete_bulletin_sync_message("rsv1", 42, BULLETIN_UID)
        mail_delete = encode_delete_mail_sync_message("rsv1", MAIL_UID)
        channel_delete = encode_delete_channel_sync_message("rsv1", CHANNEL_UID)

        _, bulletin_type, bulletin_fields = _decode_rs_message(bulletin_delete)
        _, mail_type, mail_fields = _decode_rs_message(mail_delete)
        _, channel_type, channel_fields = _decode_rs_message(channel_delete)

        assert bulletin_type == "DELETE_BULLETIN"
        assert bulletin_fields == {"identifier": BULLETIN_UID}
        assert mail_type == "DELETE_MAIL"
        assert mail_fields == {"unique_id": MAIL_UID}
        assert channel_type == "DELETE_CHANNEL"
        assert channel_fields == {"unique_id": CHANNEL_UID}

    def test_nodes_round_trip(self):
        nodes = [
            (NODE_ID, "ALICE", "Alice Node", "1700000000"),
            ("!b2c3d4e5", "BOB", "Bob Node", "1700000001"),
        ]
        message = encode_nodes_sync_message("rsv1", nodes)
        msg_type, fields = _decode_rs_message(message)[1:]
        assert msg_type == "NODES"
        assert fields == {
            "nodes": [
                {
                    "node_id": NODE_ID,
                    "short_name": "ALICE",
                    "long_name": "Alice Node",
                    "last_heard": "1700000000",
                },
                {
                    "node_id": "!b2c3d4e5",
                    "short_name": "BOB",
                    "long_name": "Bob Node",
                    "last_heard": "1700000001",
                },
            ],
        }

    def test_dedupe_mesh_node_entries_keeps_newest_last_heard(self):
        nodes = [
            (NODE_ID, "ALICE", "Alice Node", "1700000000"),
            (NODE_ID.upper(), "ALIC", "Stale Node", "1699999999"),
            ("!b2c3d4e5", "BOB", "Bob Node", "1700000001"),
        ]
        deduped = dedupe_mesh_node_entries(nodes)
        assert len(deduped) == 2
        assert deduped[0][0] == NODE_ID
        assert deduped[0][3] == "1700000000"

    def test_nodes_decode_dedupes_duplicate_ids(self):
        message = (
            'RS|1|NODES|{"n":[{"id":"!a1b2c3d4","sn":"OLD","ln":"Old","lh":"1"},'
            '{"id":"!A1B2C3D4","sn":"NEW","ln":"New","lh":"2"}]}'
        )
        msg_type, fields = _decode_rs_message(message)[1:]
        assert msg_type == "NODES"
        assert len(fields["nodes"]) == 1
        assert fields["nodes"][0]["short_name"] == "NEW"
        assert fields["nodes"][0]["last_heard"] == "2"

    def test_plan_nodes_sync_batches_splits_to_packet_limit(self):
        nodes = [
            (f"!{index:08x}", f"S{index:02d}", f"Node {index}", str(1700000000 + index))
            for index in range(12)
        ]
        batches = plan_nodes_sync_batches(nodes, "rsv1", max_packet_len=SYNC_PACKET_MAX_LEN)
        assert batches
        assert sum(len(batch) for batch in batches) == len(nodes)
        for batch in batches:
            assert len(encode_nodes_sync_message("rsv1", batch)) <= SYNC_PACKET_MAX_LEN


class TestTc2LegacyEncoding:
    def test_tc2_bulletin_uses_pipe_format(self):
        message = encode_bulletin_sync_message(
            "tc2", "general", "ALICE", "Hello", "Body", BULLETIN_UID
        )
        assert message == f"BULLETIN|general|ALICE|Hello|Body|{BULLETIN_UID}"

    def test_tc2_delete_mail_uses_pipe_format(self):
        message = encode_delete_mail_sync_message("tc2", MAIL_UID)
        assert message == f"DELETE_MAIL|{MAIL_UID}"


class TestEnvelopeParsing:
    def test_invalid_envelope_rejected(self):
        with pytest.raises(ValueError, match="Invalid RS sync message format"):
            parse_rs_envelope("BULLETIN|a|b|c")

    def test_invalid_json_payload_rejected(self):
        with pytest.raises(ValueError, match="Invalid RS sync JSON payload"):
            _decode_rs_payload(1, "BULLETIN", "not-json")


class TestChunkPlanningAndReassembly:
    def test_short_message_is_not_chunked(self):
        message = encode_bulletin_sync_message(
            "rsv1", "general", "ALICE", "Hi", "Short", BULLETIN_UID
        )
        packets = plan_sync_transmit_packets(message, "rsv1")
        assert packets == [message]

    def test_oversized_tc2_message_returns_none(self):
        message = "BULLETIN|" + ("x" * 250)
        assert plan_sync_transmit_packets(message, "tc2") is None

    def test_oversized_rs_message_is_chunked(self):
        long_body = "x" * 500
        message = encode_bulletin_sync_message(
            "rsv1", "general", "ALICE", "Big", long_body, BULLETIN_UID
        )
        packets = plan_sync_transmit_packets(message, "rsv1", SYNC_PACKET_MAX_LEN)
        assert packets is not None
        assert len(packets) > 1
        assert all(len(packet) <= SYNC_PACKET_MAX_LEN for packet in packets)

        assembler = SyncChunkAssembler()
        reassembled = _reassemble_chunks(assembler, "peer-node", packets)
        assert reassembled == message

    def test_chunk_sequence_packets_respect_limit(self):
        message = encode_bulletin_sync_message(
            "rsv1", "general", "ALICE", "Subject", "y" * 800, BULLETIN_UID
        )
        packets = build_rs_chunk_sequence(message, 1, SYNC_PACKET_MAX_LEN)
        assert len(packets) > 1
        assert all(len(packet) <= SYNC_PACKET_MAX_LEN for packet in packets)

        assembler = SyncChunkAssembler()
        assert _reassemble_chunks(assembler, "peer-node", packets) == message

    def test_chunk_reassembly_out_of_order(self):
        message = encode_bulletin_sync_message(
            "rsv1", "general", "ALICE", "Subject", "z" * 800, BULLETIN_UID
        )
        packets = build_rs_chunk_sequence(message, 1, SYNC_PACKET_MAX_LEN)
        assembler = SyncChunkAssembler()
        reassembled = _reassemble_chunks(
            assembler, "peer-node", list(reversed(packets))
        )
        assert reassembled == message

    def test_incomplete_chunk_sequence_returns_none(self):
        message = encode_bulletin_sync_message(
            "rsv1", "general", "ALICE", "Subject", "w" * 800, BULLETIN_UID
        )
        packets = build_rs_chunk_sequence(message, 1, SYNC_PACKET_MAX_LEN)
        assembler = SyncChunkAssembler()
        assert _reassemble_chunks(assembler, "peer-node", packets[:-1]) is None
