"""In-process Meshtastic interface mock for CLI client and pytest harness."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Optional


class _MockAcknowledgment:
    def __init__(self):
        self.receivedAck = False
        self.receivedImplAck = False
        self.receivedNak = False

    def reset(self):
        self.receivedAck = False
        self.receivedImplAck = False
        self.receivedNak = False


class _MockTimeout:
    sleepInterval = 0.1

    def __init__(self):
        self.expireTime = time.time() + 1

    def reset(self):
        self.expireTime = time.time() + 1


class MockSentPacket:
    def __init__(self, packet_id: int):
        self.id = packet_id


class MockMeshInterface:
    """Minimal Meshtastic StreamInterface stand-in for local BBS testing."""

    def __init__(
        self,
        bbs_node_id: str = "!aabbcc00",
        bbs_node_num: int = 1,
        bbs_short_name: str = "BBS0",
        bbs_long_name: str = "Mock BBS Node",
    ):
        self.myInfo = SimpleNamespace(my_node_num=bbs_node_num)
        self.localNode = SimpleNamespace(nodeNum=bbs_node_num)
        self.nodes: dict[str, dict[str, Any]] = {
            bbs_node_id: {
                "num": bbs_node_num,
                "user": {"shortName": bbs_short_name, "longName": bbs_long_name},
            }
        }
        self.bbs_nodes: list[str] = []
        self.sync_peers: list = []
        self.admin_nodes: list[str] = []
        self.sent_messages: list[dict[str, Any]] = []
        self.module_manager = None
        self._acknowledgment = _MockAcknowledgment()
        self._timeout = _MockTimeout()
        self._next_packet_id = 0

    def add_node(
        self,
        node_id: str,
        node_num: int,
        short_name: str,
        long_name: Optional[str] = None,
    ):
        self.nodes[node_id] = {
            "num": node_num,
            "user": {
                "shortName": short_name,
                "longName": long_name or short_name,
            },
        }

    def sendText(
        self,
        text: str,
        destinationId: Any = None,
        wantAck: bool = False,
        wantResponse: bool = False,
        onResponse=None,
    ):
        self._next_packet_id += 1
        self.sent_messages.append(
            {
                "text": text,
                "destinationId": destinationId,
                "wantAck": wantAck,
                "wantResponse": wantResponse,
            }
        )
        return MockSentPacket(self._next_packet_id)

    def close(self):
        return None
