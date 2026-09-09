#!/usr/bin/env python3
"""Interactive in-process BBS client that simulates a mesh handset."""

import argparse

from rsmesh_bbs.config_init import DEFAULT_CONFIG_FILE, get_board_name, require_config_file
from rsmesh_bbs.db_operations import initialize_database
from rsmesh_bbs.mesh_client import (
    BbsMeshClient,
    DEFAULT_CLIENT_LONG_NAME,
    DEFAULT_CLIENT_NODE_ID,
    DEFAULT_CLIENT_NODE_NUM,
    DEFAULT_CLIENT_SHORT_NAME,
)
from rsmesh_bbs.venv_guard import require_venv

require_venv()


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Simulate a mesh handset talking to the local BBS (no radio).",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help=f"Path to config.yml (default: {DEFAULT_CONFIG_FILE})",
    )
    parser.add_argument(
        "--node-id",
        default=DEFAULT_CLIENT_NODE_ID,
        help="Simulated client Meshtastic node ID (default: %(default)s)",
    )
    parser.add_argument(
        "--node-num",
        type=int,
        default=DEFAULT_CLIENT_NODE_NUM,
        help="Simulated client node number (default: %(default)s)",
    )
    parser.add_argument(
        "--short-name",
        default=DEFAULT_CLIENT_SHORT_NAME,
        help="Simulated client short name (default: %(default)s)",
    )
    parser.add_argument(
        "--long-name",
        default=DEFAULT_CLIENT_LONG_NAME,
        help="Simulated client long name (default: %(default)s)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip mesh reply pacing delays (recommended for interactive use)",
    )
    return parser.parse_args()


def _print_replies(replies):
    if not replies:
        print("(no reply)")
        return
    for reply in replies:
        print(reply)
        print()


def main():
    args = _parse_args()
    config_file = require_config_file(args.config)

    if args.fast:
        import time
        time.sleep = lambda *_args, **_kwargs: None

    initialize_database(quiet=True)
    board_name = get_board_name(config_file)
    client = BbsMeshClient.create(
        client_node_id=args.node_id,
        client_node_num=args.node_num,
        client_short_name=args.short_name,
        client_long_name=args.long_name,
    )

    print(f"RSMesh BBS client — simulating {args.short_name} ({args.node_id})")
    print(f"Board: {board_name}")
    print("Type mesh messages as you would from a handset.")
    print("Press Enter or type X for the main menu. Ctrl+C or Ctrl+D to quit.")
    print()

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                print()
                break
            if not line:
                line = "x"
            replies = client.send(line)
            _print_replies(replies)
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
