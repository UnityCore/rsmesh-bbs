import uuid

from rsmesh_bbs import db_operations


def _channel_publish(unique_id):
    row = db_operations.get_db_connection().execute(
        "SELECT publish FROM channels WHERE unique_id = ?",
        (unique_id,),
    ).fetchone()
    return row[0] if row else None


class TestChannelPublishPolicy:
    def test_mesh_post_creates_unpublished_channel(self, temp_db):
        unique_id = str(uuid.uuid4())
        db_operations.add_channel(
            "mesh-chat",
            "mesh-psk",
            [],
            None,
            defer_sync=True,
            publish="N",
            unique_id=unique_id,
        )
        assert _channel_publish(unique_id) == "N"
        assert db_operations.get_channels() == []

    def test_sync_ingest_creates_unpublished_channel(self, temp_db):
        unique_id = str(uuid.uuid4())
        db_operations.add_channel(
            "sync-chat",
            "sync-psk",
            from_sync=True,
            unique_id=unique_id,
        )
        assert _channel_publish(unique_id) == "N"
        assert db_operations.get_channels() == []

    def test_admin_add_defaults_to_published(self, temp_db):
        unique_id = str(uuid.uuid4())
        db_operations.add_channel(
            "admin-chat",
            "admin-psk",
            unique_id=unique_id,
        )
        assert _channel_publish(unique_id) == "Y"
        assert db_operations.get_channels() == [("admin-chat", "admin-psk")]

    def test_published_channel_appears_in_mesh_directory(self, temp_db):
        unique_id = str(uuid.uuid4())
        db_operations.add_channel(
            "public-chat",
            "public-psk",
            unique_id=unique_id,
            publish="Y",
        )
        assert db_operations.get_channels() == [("public-chat", "public-psk")]
