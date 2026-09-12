import uuid

from rsmesh_bbs import db_operations
from rsmesh_bbs.mesh_client import BbsMeshClient, build_text_packet
from rsmesh_bbs.mock_interface import MockMeshInterface


class TestBuildTextPacket:
    def test_build_text_packet_shape(self):
        packet = build_text_packet(100, "!abc", 1, "hello")
        assert packet["from"] == 100
        assert packet["fromId"] == "!abc"
        assert packet["to"] == 1
        assert packet["decoded"]["portnum"] == "TEXT_MESSAGE_APP"
        assert packet["decoded"]["payload"] == b"hello"


class TestMeshClientMenus:
    def test_invalid_input_shows_main_menu(self, mesh_client):
        replies = mesh_client.send("?")
        joined = "\n".join(replies)
        assert "Test BBS" in joined
        assert "[B]ulletins" in joined
        assert "[M]ail" in joined
        assert "M[o]dules" in joined

    def test_mail_submenu(self, mesh_client):
        replies = mesh_client.send_joined("m")
        assert "[R]ead Mail" in replies
        assert "[S]end Mail" in replies

    def test_mail_commands_on_main_menu(self, mesh_client, temp_db):
        from rsmesh_bbs.core_services import set_mail_commands_on_main_menu
        from rsmesh_bbs import mesh_ui

        set_mail_commands_on_main_menu(True)
        mesh_ui.regenerate_main_menu_file()
        menu = mesh_client.send_joined("?")
        assert "[R]ead Mail" in menu
        assert "[S]end Mail" in menu
        assert "[M]ail" not in menu
        replies = mesh_client.send_joined("r")
        assert "No messages." in replies
        menu = mesh_client.send_joined("?")
        assert "[R]ead Mail" in menu
        joined = mesh_client.send_joined("m")
        assert "= Mail =" not in joined
        assert "[M]ail" not in joined
        assert "[R]ead Mail" in joined

    def test_read_mail_empty_inbox(self, mesh_client):
        mesh_client.send("m")
        replies = mesh_client.send("r")
        joined = "\n".join(replies)
        assert "No messages." in joined
        assert "[R]ead Mail" in joined
        assert "[S]end Mail" in joined

    def test_read_mail_shows_message(self, mesh_client):
        unique_id = str(uuid.uuid4())
        db_operations.add_mail(
            "sender-node",
            "SNDR",
            mesh_client.client_node_id,
            "Hello",
            "Body text",
            [],
            None,
            unique_id=unique_id,
            from_sync=True,
            recipient_short_name="COFY",
        )

        mesh_client.send("m")
        replies = mesh_client.send_joined("r")
        assert "Hello" in replies
        assert "SNDR" in replies

    def test_bulletin_menu(self, mesh_client):
        replies = mesh_client.send_joined("b")
        assert "[G]eneral" in replies

    def test_modules_menu_lists_enabled_modules(self, mesh_client):
        replies = mesh_client.send_joined("o")
        assert "Modules are not available." not in replies
        assert "[F]ortune" in replies or "[I]" in replies

    def test_exit_returns_to_main_menu(self, mesh_client):
        mesh_client.send("b")
        replies = mesh_client.send_joined("x")
        assert "[B]ulletins" in replies


class TestMockMeshInterface:
    def test_send_text_records_outbound(self):
        interface = MockMeshInterface()
        interface.add_node("!0c0ffee0", 99, "COFY")
        packet = interface.sendText("hello", destinationId=99)
        assert packet.id == 1
        assert interface.sent_messages[0]["text"] == "hello"
        assert interface.sent_messages[0]["destinationId"] == 99
