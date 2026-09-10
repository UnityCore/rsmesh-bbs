import pytest

from rsmesh_bbs import db_operations
from rsmesh_bbs.message_processing import _sync_ingest_bulletin
from rsmesh_bbs.mock_interface import MockMeshInterface
from rsmesh_bbs.urgent_alerts import (
    drain_pending_urgent_alerts,
    enqueue_pending_urgent_alert,
    maybe_send_urgent_alert_local,
    normalize_yes_no,
    urgent_alert_from_sync_enabled,
    urgent_alert_local_enabled,
)


def _set_bbs_config(key, value):
    conn = db_operations.get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO sys_config (cfg_section, cfg_key, cfg_value) "
        "VALUES ('bbs', ?, ?)",
        (key, value),
    )
    conn.commit()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("yes", "yes"),
        ("Y", "yes"),
        ("no", "no"),
        ("N", "no"),
        ("", "no"),
        (None, "no"),
        ("maybe", "no"),
    ],
)
def test_normalize_yes_no(raw, expected):
    assert normalize_yes_no(raw) == expected


class TestUrgentAlertConfig:
    def test_defaults_are_disabled(self, temp_db):
        assert urgent_alert_local_enabled() is False
        assert urgent_alert_from_sync_enabled() is False

    def test_config_enables_flags(self, temp_db):
        _set_bbs_config("send_urgent_alert_local", "yes")
        _set_bbs_config("send_urgent_alert_from_sync", "yes")
        assert urgent_alert_local_enabled() is True
        assert urgent_alert_from_sync_enabled() is True


class TestUrgentAlertSending:
    def test_local_alert_respects_config(self, temp_db, monkeypatch):
        interface = MockMeshInterface()
        sent = []

        monkeypatch.setattr(
            "rsmesh_bbs.urgent_alerts.send_urgent_mesh_alert",
            lambda sender, subject, iface: sent.append((sender, subject, iface)) or True,
        )

        maybe_send_urgent_alert_local("General", "OPS", "Test", interface)
        assert sent == []

        maybe_send_urgent_alert_local("Urgent", "OPS", "Test", interface)
        assert sent == []

        _set_bbs_config("send_urgent_alert_local", "yes")
        maybe_send_urgent_alert_local("Urgent", "OPS", "Evacuate", interface)
        assert sent == [("OPS", "Evacuate", interface)]

    def test_add_bulletin_local_alert_when_enabled(self, temp_db, monkeypatch):
        interface = MockMeshInterface()
        sent = []

        monkeypatch.setattr(
            "rsmesh_bbs.urgent_alerts.send_urgent_mesh_alert",
            lambda sender, subject, iface: sent.append((sender, subject)) or True,
        )
        _set_bbs_config("send_urgent_alert_local", "yes")

        db_operations.add_bulletin(
            "Urgent", "OPS", "Storm", "Details", [], interface,
        )
        assert sent == [("OPS", "Storm")]

    def test_add_bulletin_skips_alert_when_from_sync(self, temp_db, monkeypatch):
        interface = MockMeshInterface()
        sent = []

        monkeypatch.setattr(
            "rsmesh_bbs.urgent_alerts.send_urgent_mesh_alert",
            lambda sender, subject, iface: sent.append((sender, subject)) or True,
        )
        _set_bbs_config("send_urgent_alert_local", "yes")
        _set_bbs_config("send_urgent_alert_from_sync", "yes")

        db_operations.add_bulletin(
            "Urgent", "OPS", "Storm", "Details", [], interface,
            unique_id="sync-uid-1", from_sync=True,
        )
        assert sent == []

    def test_sync_ingest_alert_when_enabled(self, temp_db, monkeypatch):
        interface = MockMeshInterface()
        sent = []

        monkeypatch.setattr(
            "rsmesh_bbs.urgent_alerts.send_urgent_mesh_alert",
            lambda sender, subject, iface: sent.append((sender, subject)) or True,
        )
        _set_bbs_config("send_urgent_alert_from_sync", "yes")

        _sync_ingest_bulletin(
            "Urgent", "PEER", "Incoming", "Body", "sync-uid-2", interface,
        )
        assert sent == [("PEER", "Incoming")]


class TestPendingUrgentAlerts:
    def test_enqueue_only_when_config_yes_at_add_time(self, temp_db):
        unique_id = db_operations.add_bulletin(
            "Urgent", "OPS", "Queued", "Body", None, None,
        )
        conn = db_operations.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM pending_urgent_alerts WHERE unique_id = ?", (unique_id,))
        assert c.fetchone()[0] == 0

        _set_bbs_config("send_urgent_alert_local", "yes")
        assert enqueue_pending_urgent_alert(unique_id, "OPS", "Queued") is True
        c.execute("SELECT COUNT(*) FROM pending_urgent_alerts WHERE unique_id = ?", (unique_id,))
        assert c.fetchone()[0] == 1
        assert enqueue_pending_urgent_alert(unique_id, "OPS", "Queued") is False

    def test_drain_sends_and_removes_row(self, temp_db, monkeypatch):
        interface = MockMeshInterface()
        sent = []

        monkeypatch.setattr(
            "rsmesh_bbs.urgent_alerts.send_urgent_mesh_alert",
            lambda sender, subject, iface: sent.append(subject) or True,
        )
        unique_id = db_operations.add_bulletin(
            "Urgent", "OPS", "Queued", "Body", None, None,
        )
        _set_bbs_config("send_urgent_alert_local", "yes")
        enqueue_pending_urgent_alert(unique_id, "OPS", "Queued")

        drain_pending_urgent_alerts(interface)
        assert sent == ["Queued"]

        conn = db_operations.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM pending_urgent_alerts")
        assert c.fetchone()[0] == 0

    def test_drain_drops_when_config_disabled(self, temp_db):
        interface = MockMeshInterface()
        unique_id = db_operations.add_bulletin(
            "Urgent", "OPS", "Queued", "Body", None, None,
        )
        enqueue_pending_urgent_alert(unique_id, "OPS", "Queued")

        drain_pending_urgent_alerts(interface)

        conn = db_operations.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM pending_urgent_alerts")
        assert c.fetchone()[0] == 0

    def test_drain_drops_when_bulletin_deleted(self, temp_db, monkeypatch):
        interface = MockMeshInterface()
        monkeypatch.setattr(
            "rsmesh_bbs.urgent_alerts.send_urgent_mesh_alert",
            lambda *_args, **_kwargs: True,
        )
        _set_bbs_config("send_urgent_alert_local", "yes")
        unique_id = db_operations.add_bulletin(
            "Urgent", "OPS", "Queued", "Body", None, None,
        )
        enqueue_pending_urgent_alert(unique_id, "OPS", "Queued")

        conn = db_operations.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM bulletins WHERE unique_id = ?", (unique_id,))
        bulletin_id = c.fetchone()[0]
        db_operations.mark_bulletin_deleted(bulletin_id)

        drain_pending_urgent_alerts(interface)

        c.execute("SELECT COUNT(*) FROM pending_urgent_alerts")
        assert c.fetchone()[0] == 0
