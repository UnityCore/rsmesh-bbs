"""In-process mesh handset simulator for the BBS command flow."""

from __future__ import annotations

from typing import Any, Optional

from .db_operations import reload_admin_nodes, reload_sync_peers
from .message_processing import on_receive
from .mock_interface import MockMeshInterface
from .module_loader import ModuleManager
from .node_resolution import scan_mesh_nodes_store
from .utils import drain_outbound_user_messages


DEFAULT_CLIENT_NODE_ID = "!0c0ffee0"
DEFAULT_CLIENT_NODE_NUM = 0x0C0FFEE0
DEFAULT_CLIENT_SHORT_NAME = "COFY"
DEFAULT_CLIENT_LONG_NAME = "CLI Test User"

DEFAULT_BBS_NODE_ID = "!aabbcc00"
DEFAULT_BBS_SHORT_NAME = "BBS0"
DEFAULT_BBS_LONG_NAME = "RSMesh Virtual Radio"


def node_id_to_num(node_id: str, fallback: int = DEFAULT_CLIENT_NODE_NUM) -> int:
    node_id = (node_id or "").strip()
    if node_id.startswith("!"):
        try:
            return int(node_id[1:], 16)
        except ValueError:
            pass
    return fallback


def build_text_packet(
    from_num: int,
    from_id: str,
    to_num: int,
    text: str,
) -> dict[str, Any]:
    """Build a Meshtastic TEXT_MESSAGE_APP packet dict for on_receive()."""
    return {
        "from": from_num,
        "fromId": from_id,
        "to": to_num,
        "decoded": {
            "portnum": "TEXT_MESSAGE_APP",
            "payload": text.encode("utf-8"),
        },
    }


class BbsMeshClient:
    """Simulate a mesh user sending direct messages to the BBS."""

    def __init__(
        self,
        interface: MockMeshInterface,
        client_node_id: str,
        client_node_num: int,
    ):
        self.interface = interface
        self.client_node_id = client_node_id
        self.client_node_num = client_node_num

    @classmethod
    def create(
        cls,
        *,
        client_node_id: str = DEFAULT_CLIENT_NODE_ID,
        client_node_num: int = DEFAULT_CLIENT_NODE_NUM,
        client_short_name: str = DEFAULT_CLIENT_SHORT_NAME,
        client_long_name: str = DEFAULT_CLIENT_LONG_NAME,
        bbs_node_id: str = DEFAULT_BBS_NODE_ID,
        bbs_node_num: Optional[int] = None,
        bbs_short_name: str = DEFAULT_BBS_SHORT_NAME,
        bbs_long_name: str = DEFAULT_BBS_LONG_NAME,
    ) -> "BbsMeshClient":
        if bbs_node_num is None:
            bbs_node_num = node_id_to_num(bbs_node_id, fallback=1)
        interface = MockMeshInterface(
            bbs_node_id=bbs_node_id,
            bbs_node_num=bbs_node_num,
            bbs_short_name=bbs_short_name,
            bbs_long_name=bbs_long_name,
        )
        interface.add_node(
            client_node_id,
            client_node_num,
            client_short_name,
            client_long_name,
        )
        reload_sync_peers(interface)
        reload_admin_nodes(interface)
        scan_mesh_nodes_store(interface)
        module_manager = ModuleManager()
        module_manager.load_modules(interface)
        interface.module_manager = module_manager
        return cls(interface, client_node_id, client_node_num)

    def _is_to_client(self, sent: dict[str, Any]) -> bool:
        destination = sent.get("destinationId")
        if destination == self.client_node_num:
            return True
        if destination == self.client_node_id:
            return True
        if isinstance(destination, str) and destination.isdigit():
            return int(destination) == self.client_node_num
        return False

    def send(self, message: str) -> list[str]:
        """Send one user message and return all BBS reply text chunks."""
        mark = len(self.interface.sent_messages)
        packet = build_text_packet(
            from_num=self.client_node_num,
            from_id=self.client_node_id,
            to_num=self.interface.myInfo.my_node_num,
            text=message,
        )
        on_receive(packet, self.interface)
        drain_outbound_user_messages()
        return [
            sent["text"]
            for sent in self.interface.sent_messages[mark:]
            if self._is_to_client(sent)
        ]

    def send_joined(self, message: str, separator: str = "\n") -> str:
        """Send a message and return replies joined into one string."""
        return separator.join(self.send(message))

    def clear_sent(self):
        self.interface.sent_messages.clear()
