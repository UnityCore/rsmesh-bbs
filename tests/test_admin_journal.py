import logging
from pathlib import Path

import pytest

from rsmesh_bbs import admin_journal


def test_resolve_server_log_path_from_config(temp_db, tmp_path):
    from rsmesh_bbs.db_operations import add_sys_config_entry

    config_file = tmp_path / "config.yml"
    config_file.write_text("bbs:\n  board_name: Test\n", encoding="utf-8")
    add_sys_config_entry("admin", "server_log_file", "logs/server.log")

    path = admin_journal.resolve_server_log_path(str(config_file))
    assert path == tmp_path / "logs" / "server.log"


def test_resolve_server_log_path_default_file(temp_db, tmp_path):
    config_file = tmp_path / "config.yml"
    config_file.write_text("bbs:\n  board_name: Test\n", encoding="utf-8")
    log_file = tmp_path / admin_journal.DEFAULT_LOG_FILE
    log_file.write_text("hello\n", encoding="utf-8")

    path = admin_journal.resolve_server_log_path(str(config_file))
    assert path == log_file


def test_server_log_view_available_uses_configured_file(temp_db):
    from rsmesh_bbs.db_operations import add_sys_config_entry

    add_sys_config_entry("admin", "server_log_file", "rsmesh-bbs.log")
    assert admin_journal.server_log_view_available() is True


def test_server_log_view_available_uses_existing_default_file(temp_db, tmp_path, monkeypatch):
    config_file = tmp_path / "config.yml"
    config_file.write_text("bbs:\n  board_name: Test\n", encoding="utf-8")
    log_file = tmp_path / admin_journal.DEFAULT_LOG_FILE
    log_file.write_text("hello\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert admin_journal.server_log_view_available(str(config_file)) is True


def test_follow_server_log_uses_resolved_file(tmp_path, monkeypatch):
    log_file = tmp_path / "server.log"
    log_file.write_text("line one\n", encoding="utf-8")
    monkeypatch.setattr(
        admin_journal,
        "resolve_server_log_path",
        lambda config_file=None: log_file,
    )

    seen = []

    def _fake_follow_log_file(path):
        seen.append(path)
        return True, None

    monkeypatch.setattr(admin_journal, "follow_log_file", _fake_follow_log_file)
    ok, message = admin_journal.follow_server_log()
    assert ok is True
    assert message is None
    assert seen == [log_file]


def test_follow_server_log_missing_configuration(monkeypatch):
    monkeypatch.setattr(admin_journal, "resolve_server_log_path", lambda config_file=None: None)
    ok, message = admin_journal.follow_server_log()
    assert ok is False
    assert message is not None
    assert "server_log_file" in message


def test_follow_log_file_missing():
    ok, message = admin_journal.follow_log_file(Path("/no/such/file.log"))
    assert ok is False
    assert "not found" in (message or "")


def test_follow_log_file_tail_and_ctrl_c(tmp_path):
    log_file = tmp_path / "server.log"
    log_file.write_text("older\nnewer\n", encoding="utf-8")

    calls = {"count": 0}

    def _fake_sleep(_seconds):
        calls["count"] += 1
        if calls["count"] >= 1:
            raise KeyboardInterrupt

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(admin_journal.time, "sleep", _fake_sleep)
    try:
        ok, message = admin_journal.follow_log_file(log_file)
    finally:
        monkeypatch.undo()

    assert ok is True
    assert message is None


def test_attach_server_file_logging_adds_handler(temp_db, tmp_path):
    from rsmesh_bbs.db_operations import add_sys_config_entry

    config_file = tmp_path / "config.yml"
    config_file.write_text("bbs:\n  board_name: Test\n", encoding="utf-8")
    add_sys_config_entry("admin", "server_log_file", "logs/server.log")

    root = logging.getLogger()
    before = len(root.handlers)
    path = admin_journal.attach_server_file_logging(str(config_file))
    after = len(root.handlers)

    assert path == tmp_path / "logs" / "server.log"
    assert path.is_file()
    assert after == before + 1

    root.handlers = root.handlers[:before]
