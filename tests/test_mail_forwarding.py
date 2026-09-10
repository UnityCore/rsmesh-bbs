import uuid
from datetime import datetime

from rsmesh_bbs import db_operations


def _add_catalog_node(short_name, node_hex, forward_to=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = db_operations.get_db_connection()
    conn.execute(
        "INSERT INTO node_catalog "
        "(long_name, short_name, node_hex_username, bbs_mail_forward_to, created, updated) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (short_name, short_name, node_hex, forward_to, now, now),
    )
    conn.commit()


class TestMailForwarding:
    def test_forwards_mail_to_catalog_target(self, temp_db):
        _add_catalog_node("ALICE", "!alice01", "!bob01")
        _add_catalog_node("BOB", "!bob01", None)

        recipient_id, content = db_operations.apply_mail_forwarding(
            "!alice01", "Hello there", interface=None
        )
        assert recipient_id == "!bob01"
        assert content.endswith("Sent to ALICE")

    def test_unresolved_forward_target_delivers_to_original(self, temp_db):
        _add_catalog_node("ALICE", "!alice01", "UNKNOWN")

        recipient_id, content = db_operations.apply_mail_forwarding(
            "!alice01", "Hello", interface=None
        )
        assert recipient_id == "!alice01"
        assert content == "Hello"

    def test_add_mail_applies_forwarding(self, temp_db):
        _add_catalog_node("ALICE", "!alice01", "!bob01")
        _add_catalog_node("BOB", "!bob01", None)
        unique_id = str(uuid.uuid4())

        db_operations.add_mail(
            "!sender01",
            "SND",
            "!alice01",
            "Subject",
            "Packet",
            [],
            None,
            unique_id=unique_id,
        )

        conn = db_operations.get_db_connection()
        row = conn.execute(
            "SELECT recipient, content FROM mail WHERE unique_id = ?", (unique_id,)
        ).fetchone()
        assert row[0] == "!bob01"
        assert "Sent to ALICE" in row[1]
