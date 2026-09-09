#!/usr/bin/env python3
"""Interactive in-process BBS client that simulates a mesh handset."""

import argparse

from rsmesh_bbs.admin_ui import clear_screen, input_bold, print_header_line, print_separator
from rsmesh_bbs.config_init import (
    DEFAULT_CLIENT_CONFIG_FILE,
    client_setup_paths,
    get_board_name,
    get_client_settings,
    missing_client_setup_files,
    print_incomplete_setup_error,
)
from rsmesh_bbs.db_operations import initialize_database
from rsmesh_bbs.mesh_client import BbsMeshClient, node_id_to_num
from rsmesh_bbs.venv_guard import require_venv

require_venv()


def _preparse_config_arg():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--config", "-c",
        default=None,
        help=f"Path to config_client.yml (default: {DEFAULT_CLIENT_CONFIG_FILE})",
    )
    return pre_parser.parse_known_args()


def _parse_args(remaining, config_file, client_config_file):
    client_settings = get_client_settings(client_config_file)
    node_id_default = client_settings["node_id"]
    short_name_default = client_settings["short_name"]
    long_name_default = client_settings["long_name"]

    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--config", "-c",
        default=None,
        help=f"Path to config_client.yml (default: {DEFAULT_CLIENT_CONFIG_FILE})",
    )
    parser = argparse.ArgumentParser(
        description="Simulate a mesh handset talking to the local BBS (no radio).",
        parents=[pre_parser],
    )
    parser.add_argument(
        "--node-id",
        default=node_id_default,
        help="Simulated client Meshtastic node ID (default: from config_client.yml)",
    )
    parser.add_argument(
        "--node-num",
        type=int,
        default=node_id_to_num(node_id_default),
        help="Simulated client node number (default: derived from node ID)",
    )
    parser.add_argument(
        "--short-name",
        default=short_name_default,
        help="Simulated client short name (default: from config_client.yml)",
    )
    parser.add_argument(
        "--long-name",
        default=long_name_default,
        help="Simulated client long name (default: from config_client.yml)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip mesh reply pacing delays (recommended for interactive use)",
    )
    args = parser.parse_args(remaining)
    return args, config_file


def _print_replies(replies):
    if not replies:
        print("(no reply)")
        return
    for reply in replies:
        print(reply)
        print()


def main() -> int:
    pre_args, remaining = _preparse_config_arg()
    missing = missing_client_setup_files(client_config_file=pre_args.config)
    if missing:
        print_incomplete_setup_error(missing)
        return 1

    config_path, client_path = client_setup_paths(client_config_file=pre_args.config)
    args, config_file = _parse_args(remaining, str(config_path), str(client_path))

    if args.fast:
        import time
        time.sleep = lambda *_args, **_kwargs: None

    initialize_database(quiet=True)
    client = BbsMeshClient.create(
        client_node_id=args.node_id,
        client_node_num=args.node_num,
        client_short_name=args.short_name,
        client_long_name=args.long_name,
    )

    clear_screen()
    board_name = get_board_name(config_file)
    header = f"{board_name} Client : Node {args.short_name} ({args.node_id})"
    print_header_line(header)
    print_separator()
    print("Type mesh messages as you would from a handset.")
    print("Press Enter or type X for the main menu. Ctrl+C or Ctrl+D to quit.")
    print()

    prompt = f"{args.short_name}> "
    try:
        while True:
            try:
                line = input_bold(prompt).strip()
            except EOFError:
                print()
                break
            if not line:
                line = "x"
            replies = client.send(line)
            _print_replies(replies)
    except KeyboardInterrupt:
        print("\nBye.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
