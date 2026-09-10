import pytest

from rsmesh_bbs.admin_ui import format_header_line
from rsmesh_bbs.config_init import (
    get_client_settings,
    load_client_config,
    missing_client_setup_files,
    print_incomplete_setup_error,
    require_client_setup,
)
from rsmesh_bbs.mesh_client import node_id_to_num


class TestFormatHeaderLine:
    def test_version_right_aligned_at_column_79(self):
        line = format_header_line("RSTest BBS Client : Node COFY (!0c0ffee0)", "1.1")
        assert len(line) == 79
        assert line.endswith("1.1")
        assert line.startswith("RSTest BBS Client")


class TestClientConfig:
    def test_load_client_config(self, tmp_path):
        config_path = tmp_path / "config_client.yml"
        config_path.write_text(
            "client:\n"
            "  node_id: \"!deadbeef\"\n"
            "  short_name: TEST\n",
            encoding="utf-8",
        )

        config = load_client_config(str(config_path))
        assert config["client"]["node_id"] == "!deadbeef"
        assert config["client"]["short_name"] == "TEST"

    def test_get_client_settings_uses_defaults_for_missing_keys(self, tmp_path):
        config_path = tmp_path / "config_client.yml"
        config_path.write_text("client: {}\n", encoding="utf-8")

        settings = get_client_settings(str(config_path))
        assert settings["node_id"] == "!0c0ffee0"
        assert settings["short_name"] == "COFY"
        assert settings["long_name"] == "CLI Test User"

    def test_get_client_settings_reads_long_name(self, tmp_path):
        config_path = tmp_path / "config_client.yml"
        config_path.write_text(
            "client:\n"
            "  long_name: Alice Handset\n",
            encoding="utf-8",
        )

        settings = get_client_settings(str(config_path))
        assert settings["long_name"] == "Alice Handset"


class TestRequireClientSetup:
    def test_require_client_setup_returns_paths(self, tmp_path):
        config_path = tmp_path / "config.yml"
        client_path = tmp_path / "config_client.yml"
        config_path.write_text("bbs:\n  board_name: Test\n", encoding="utf-8")
        client_path.write_text("client: {}\n", encoding="utf-8")

        assert require_client_setup(str(config_path), str(client_path)) == (
            str(config_path),
            str(client_path),
        )

    def test_missing_client_setup_files_lists_all_missing(self, tmp_path):
        config_path = tmp_path / "config.yml"
        client_path = tmp_path / "config_client.yml"

        missing = missing_client_setup_files(str(config_path), str(client_path))
        assert missing == [str(config_path), str(client_path)]

    def test_print_incomplete_setup_error_reports_missing_files(self, tmp_path, capsys):
        config_path = tmp_path / "config.yml"
        client_path = tmp_path / "config_client.yml"

        print_incomplete_setup_error([str(config_path), str(client_path)])

        err = capsys.readouterr().err
        assert "board setup is incomplete" in err
        assert "config.yml" in err
        assert "config_client.yml" in err

    def test_require_client_setup_exits_on_missing_files(self, tmp_path, capsys):
        config_path = tmp_path / "config.yml"
        client_path = tmp_path / "config_client.yml"

        with pytest.raises(SystemExit) as exc:
            require_client_setup(str(config_path), str(client_path))
        assert exc.value.code == 1

        err = capsys.readouterr().err
        assert "board setup is incomplete" in err

    def test_require_client_setup_reports_single_missing_file(self, tmp_path, capsys):
        config_path = tmp_path / "config.yml"
        client_path = tmp_path / "config_client.yml"
        config_path.write_text("bbs:\n  board_name: Test\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            require_client_setup(str(config_path), str(client_path))
        assert exc.value.code == 1

        err = capsys.readouterr().err
        assert "board setup is incomplete" in err
        assert "Missing configuration file:" in err
        assert str(client_path) in err


class TestClientMainExit:
    def test_main_returns_error_when_setup_incomplete(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        import importlib.util
        from pathlib import Path

        script_path = Path(__file__).resolve().parents[1] / "rsmesh-bbs_client.py"
        spec = importlib.util.spec_from_file_location("rsmesh_bbs_client", script_path)
        client_module = importlib.util.module_from_spec(spec)
        monkeypatch.setattr(
            "rsmesh_bbs.venv_guard.require_venv",
            lambda: None,
            raising=False,
        )
        spec.loader.exec_module(client_module)

        assert client_module.main() == 1


class TestNodeIdToNum:
    def test_node_id_to_num_parses_hex(self):
        assert node_id_to_num("!0c0ffee0") == 0x0C0FFEE0

    def test_node_id_to_num_falls_back_on_invalid(self):
        assert node_id_to_num("!not-hex", fallback=42) == 42
