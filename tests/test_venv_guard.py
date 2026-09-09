import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from rsmesh_bbs.preflight import run_server_preflight
from rsmesh_bbs.venv_guard import is_running_in_venv, require_venv


class TestVenvGuard:
    def test_is_running_in_venv_when_prefixes_differ(self):
        with patch.object(sys, "prefix", "/venv"), patch.object(sys, "base_prefix", "/usr"):
            assert is_running_in_venv() is True

    def test_is_running_in_venv_when_prefixes_match(self):
        with patch.object(sys, "prefix", "/usr"), patch.object(sys, "base_prefix", "/usr"):
            assert is_running_in_venv() is False

    def test_is_running_in_venv_when_executable_under_dot_venv(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "executable",
            "/opt/rsmesh-bbs/.venv/bin/python",
        )
        with patch.object(sys, "prefix", "/usr"), patch.object(sys, "base_prefix", "/usr"):
            assert is_running_in_venv() is True

    def test_require_venv_exits_outside_venv(self):
        with patch.object(sys, "prefix", "/usr"), patch.object(sys, "base_prefix", "/usr"):
            with patch.object(sys, "executable", "/usr/bin/python3"):
                try:
                    require_venv()
                except SystemExit as exc:
                    assert exc.code == 1
                else:
                    raise AssertionError("expected SystemExit")

    def test_require_venv_allows_venv(self):
        with patch.object(sys, "prefix", "/venv"), patch.object(sys, "base_prefix", "/usr"):
            require_venv()


class TestServerPreflight:
    def test_preflight_requires_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        venv_python = venv_bin / "python"
        venv_python.write_text("", encoding="utf-8")
        monkeypatch.setattr(sys, "executable", str(venv_python))

        with pytest.raises(SystemExit) as exc:
            run_server_preflight()
        assert exc.value.code == 1

    def test_preflight_detects_readonly_database(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        venv_python = venv_bin / "python"
        venv_python.write_text("", encoding="utf-8")
        monkeypatch.setattr(sys, "executable", str(venv_python))
        config_path = tmp_path / "config.yml"
        config_path.write_text("bbs:\n  board_name: Test\n", encoding="utf-8")
        db_path = tmp_path / "rsmesh-bbs.db"
        db_path.write_text("", encoding="utf-8")
        db_path.chmod(0o444)

        with pytest.raises(SystemExit) as exc:
            run_server_preflight(str(config_path))
        assert exc.value.code == 1
