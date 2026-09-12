import uuid

from rsmesh_bbs import db_operations
from rsmesh_bbs.core_services import (
    CORE_BULLETINS_KEY,
    CORE_MAIL_KEY,
    ensure_core_services_config,
    set_core_service_enabled,
)
from rsmesh_bbs.message_processing import _inbound_sync_allowed, _process_sync_message
from rsmesh_bbs.mock_interface import MockMeshInterface


def _seed_core_services():
    db_operations.ensure_sys_config_from_yaml()
    ensure_core_services_config()


def _setup_peer(interface, peer_node="!peer_a"):
    db_operations.add_sync_peer(
        peer_node,
        sync_protocol="tc2",
        sync_bulletins="Y",
        ingest_bulletins="Y",
    )
    interface.bbs_nodes = [peer_node]
    db_operations.reload_sync_peers(interface)


class TestCoreServicesInboundSync:
    def test_inbound_bulletin_blocked_when_core_service_off(self, temp_db):
        _seed_core_services()
        interface = MockMeshInterface()
        _setup_peer(interface)
        set_core_service_enabled(CORE_BULLETINS_KEY, False)

        assert not _inbound_sync_allowed("!peer_a", interface, "bulletins")

    def test_inbound_bulletin_ingest_skipped_when_core_service_off(self, temp_db):
        _seed_core_services()
        interface = MockMeshInterface()
        _setup_peer(interface)
        set_core_service_enabled(CORE_BULLETINS_KEY, False)

        unique_id = str(uuid.uuid4())
        message = f"BULLETIN|General|OPS|Subject|Body|{unique_id}"
        _process_sync_message(0, message, interface, "!peer_a")

        conn = db_operations.get_db_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM bulletins WHERE unique_id = ?",
            (unique_id,),
        ).fetchone()
        assert row[0] == 0


class TestCoreServicesOutboundSync:
    def test_sync_pending_skips_bulletins_when_core_service_off(self, temp_db):
        _seed_core_services()
        interface = MockMeshInterface()
        _setup_peer(interface)

        unique_id = db_operations.add_bulletin(
            "General", "OPS", "Subject", "Body", interface.bbs_nodes, interface, defer_sync=True,
        )
        assert unique_id

        set_core_service_enabled(CORE_BULLETINS_KEY, False)
        before = len(interface.sent_messages)
        db_operations.sync_pending_records(interface.sync_peers, interface)
        assert len(interface.sent_messages) == before

        set_core_service_enabled(CORE_BULLETINS_KEY, True)
        db_operations.sync_pending_records(interface.sync_peers, interface)
        assert len(interface.sent_messages) > before

    def test_sync_bulletin_record_noop_when_core_service_off(self, temp_db):
        _seed_core_services()
        interface = MockMeshInterface()
        _setup_peer(interface)

        unique_id = db_operations.add_bulletin(
            "General", "OPS", "Subject", "Body", interface.bbs_nodes, interface, defer_sync=True,
        )
        set_core_service_enabled(CORE_BULLETINS_KEY, False)
        before = len(interface.sent_messages)
        db_operations.sync_bulletin_record(unique_id, interface.bbs_nodes, interface)
        assert len(interface.sent_messages) == before


class TestCoreServicesSchedule:
    def test_purge_deleted_bulletins_skipped_when_core_service_off(self, temp_db):
        _seed_core_services()
        interface = MockMeshInterface()
        _setup_peer(interface)

        unique_id = db_operations.add_bulletin(
            "General", "OPS", "Subject", "Body", None, None, defer_sync=True,
        )
        conn = db_operations.get_db_connection()
        conn.execute(
            "UPDATE bulletins SET deleted = 'Y', delete_reconcile = 'N' WHERE unique_id = ?",
            (unique_id,),
        )
        conn.commit()

        set_core_service_enabled(CORE_BULLETINS_KEY, False)
        db_operations.purge_deleted_bulletins(interface.bbs_nodes, interface)
        remaining = conn.execute(
            "SELECT COUNT(*) FROM bulletins WHERE deleted = 'Y'",
        ).fetchone()[0]
        assert remaining == 1

        set_core_service_enabled(CORE_BULLETINS_KEY, True)
        db_operations.purge_deleted_bulletins(interface.bbs_nodes, interface)
        remaining = conn.execute(
            "SELECT COUNT(*) FROM bulletins WHERE deleted = 'Y'",
        ).fetchone()[0]
        assert remaining == 0

    def test_unsynced_records_excludes_disabled_core_services(self, temp_db):
        _seed_core_services()
        db_operations.add_bulletin(
            "General", "OPS", "Subject", "Body", None, None, defer_sync=True,
        )
        db_operations.add_mail(
            "!sender", "SNDR", "!recipient", "Hello", "Body", None, None, defer_sync=True,
        )

        bulletins, mail_rows, channels = db_operations.get_unsynced_records()
        assert bulletins
        assert mail_rows

        set_core_service_enabled(CORE_BULLETINS_KEY, False)
        set_core_service_enabled(CORE_MAIL_KEY, False)
        bulletins, mail_rows, channels = db_operations.get_unsynced_records()
        assert bulletins == []
        assert mail_rows == []
