"""Read-only BBS identity helpers for core code and modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .config_init import get_board_name


@dataclass(frozen=True)
class BbsInfo:
    board_name: str
    node_id: Optional[str] = None
    short_name: Optional[str] = None
    long_name: Optional[str] = None

    @property
    def radio_configured(self) -> bool:
        return bool(self.node_id or self.short_name or self.long_name)


def _strip_or_none(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _radio_from_sys_config() -> tuple[Optional[str], Optional[str], Optional[str]]:
    from .db_operations import get_sys_config_value

    return (
        _strip_or_none(get_sys_config_value("interface", "node_id")),
        _strip_or_none(get_sys_config_value("interface", "short_name")),
        _strip_or_none(get_sys_config_value("interface", "long_name")),
    )


def _radio_from_interface(interface) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if interface is None:
        return None, None, None
    local_node = getattr(interface, "localNode", None)
    local_num = getattr(local_node, "nodeNum", None)
    if local_num is None:
        return None, None, None

    from .utils import get_node_id_from_num

    node_id = get_node_id_from_num(local_num, interface)
    if not node_id:
        return None, None, None
    node = getattr(interface, "nodes", {}).get(node_id, {})
    user = node.get("user", {})
    return (
        node_id,
        _strip_or_none(user.get("shortName")),
        _strip_or_none(user.get("longName")),
    )


def get_bbs_info(interface=None, config_file: Optional[str] = None) -> BbsInfo:
    board_name = get_board_name(config_file)
    cfg_node_id, cfg_short_name, cfg_long_name = _radio_from_sys_config()
    live_node_id, live_short_name, live_long_name = _radio_from_interface(interface)

    return BbsInfo(
        board_name=board_name,
        node_id=cfg_node_id or live_node_id,
        short_name=cfg_short_name or live_short_name,
        long_name=cfg_long_name or live_long_name,
    )
