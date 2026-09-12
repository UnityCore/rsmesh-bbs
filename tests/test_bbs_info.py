from rsmesh_bbs import db_operations
from rsmesh_bbs.bbs_info import get_bbs_info
from rsmesh_bbs.config_init import get_board_name
from rsmesh_bbs.mock_interface import MockMeshInterface


class TestBbsInfo:
    def test_get_board_name_reads_sys_config(self, temp_db):
        db_operations.ensure_sys_config_from_yaml()
        db_operations.update_sys_config_entry("bbs", "board_name", "Mesh Test BBS")

        assert get_board_name() == "Mesh Test BBS"

    def test_get_bbs_info_uses_sys_config_radio_fields(self, temp_db):
        db_operations.ensure_sys_config_from_yaml()
        db_operations.update_sys_config_entry("interface", "node_id", "!17d7e4b7")
        db_operations.update_sys_config_entry("interface", "short_name", "BBS1")
        db_operations.update_sys_config_entry("interface", "long_name", "Example BBS")

        info = get_bbs_info()

        assert info.board_name
        assert info.node_id == "!17d7e4b7"
        assert info.short_name == "BBS1"
        assert info.long_name == "Example BBS"
        assert info.radio_configured is True

    def test_get_bbs_info_falls_back_to_connected_radio(self, temp_db):
        db_operations.ensure_sys_config_from_yaml()
        interface = MockMeshInterface(
            bbs_node_id="!aabbcc00",
            bbs_short_name="BBS0",
            bbs_long_name="Virtual Radio",
        )

        info = get_bbs_info(interface)

        assert info.node_id == "!aabbcc00"
        assert info.short_name == "BBS0"
        assert info.long_name == "Virtual Radio"
