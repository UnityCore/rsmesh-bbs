#!/usr/bin/env python3

"""
RSMesh BBS

Based on TC²-BBS Server for Meshtastic by TheCommsChannel (TC²) v0.1.6

Description:
The system allows for mail message handling, bulletin boards, and a channel
directory. It uses a configuration file for setup details and an SQLite3
database for data storage. Mail messages and bulletins are synced with
other BBS servers listed in the configuration file.
"""

import logging
import sys
import time
import threading

from rsmesh_bbs.venv_guard import require_venv

require_venv()

from rsmesh_bbs.version import APP_NAME, VERSION

from rsmesh_bbs.config_init import initialize_config, get_interface, init_cli_parser, format_board_banner, DEFAULT_CONFIG_FILE
from rsmesh_bbs.preflight import run_server_preflight
from rsmesh_bbs.tc2_migration import prepare_tc2_upgrade, import_tc2_sync_peers_from_ini
from rsmesh_bbs.core_services import ensure_core_services_config
from rsmesh_bbs.db_operations import (
    initialize_database,
    ensure_superuser_sysadmin,
    reload_admin_nodes,
    purge_deleted_bulletins,
    purge_deleted_channels,
    get_sync_peers,
    reload_sync_peers,
    sync_pending_records,
    normalize_sync_peer_last_heard,
    ensure_sys_config_from_yaml,
    get_peer_sync_seconds,
    get_sync_purge_seconds,
    get_module_exec_seconds,
    get_eventbus_topic,
)
from rsmesh_bbs.module_loader import ModuleManager
from rsmesh_bbs.time_format import format_relative_time
from rsmesh_bbs.utils import join_display_fields, drain_outbound_user_messages
from rsmesh_bbs.urgent_alerts import drain_pending_urgent_alerts
from rsmesh_bbs.message_processing import on_receive
from rsmesh_bbs.node_resolution import scan_mesh_nodes_store
from pubsub import pub

# General logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def display_banner(board_name):
    print(format_board_banner(board_name))

def main():
    args = init_cli_parser()
    config_file = args.config if args.config is not None else DEFAULT_CONFIG_FILE
    prepare_tc2_upgrade(config_file)
    run_server_preflight(config_file)
    system_config = initialize_config(config_file)
    display_banner(system_config['board_name'])

    initialize_database()
    ensure_sys_config_from_yaml(config_file)
    ensure_core_services_config(config_file)
    import_tc2_sync_peers_from_ini()

    interface = get_interface(system_config)
    module_manager = ModuleManager()
    module_manager.load_modules(interface)
    interface.module_manager = module_manager
    reload_sync_peers(interface)
    if interface.sync_peers:
        print("Configured sync peers:")
        for peer in interface.sync_peers:
            peer_id, bbs_node, bbs_name, sync_protocol, last_heard = peer[:5]
            name_part = f" ({bbs_name})" if bbs_name else ""
            heard = format_relative_time(normalize_sync_peer_last_heard(last_heard))
            out_flags = (
                f"B:{(peer[5] if len(peer) > 5 else 'Y')}/"
                f"M:{(peer[6] if len(peer) > 6 else 'Y')}/"
                f"C:{(peer[7] if len(peer) > 7 else 'Y')}/"
                f"N:{(peer[8] if len(peer) > 8 else 'N')}"
            )
            in_flags = (
                f"B:{(peer[9] if len(peer) > 9 else 'Y')}/"
                f"M:{(peer[6] if len(peer) > 6 else 'Y')}/"
                f"C:{(peer[10] if len(peer) > 10 else 'Y')}"
            )
            enabled = peer[13] if len(peer) > 13 else 'Y'
            print(
                "  " + join_display_fields(
                    f"[{peer_id}] {bbs_node}{name_part} ({sync_protocol})",
                    f"enabled {enabled or 'Y'}",
                    f"last heard {heard}",
                    f"sync out {out_flags}",
                    f"in {in_flags}",
                )
            )
    else:
        print("No sync peers configured.")
    superuser_node = system_config['superuser_node']
    added, short_name = ensure_superuser_sysadmin(superuser_node)
    if added:
        print(
            f"Superuser node {superuser_node} was not in sysadmin_nodes; "
            f"added with short name {short_name}."
        )
    admin_nodes = reload_admin_nodes(interface)
    if admin_nodes:
        print(f"Nodes with SysAdmin permissions: {admin_nodes}")
    else:
        print("No SysAdmin nodes configured")

    logging.info(f"{APP_NAME} {VERSION} running on {system_config['interface_type']} interface...")

    def receive_packet(packet, interface):
        on_receive(packet, interface)

    pub.subscribe(receive_packet, get_eventbus_topic())
    scan_mesh_nodes_store(interface)

    def module_schedule_worker():
        while True:
            try:
                module_manager.run_due_schedules(interface)
            except Exception as e:
                logging.error(f"Error in module schedule worker: {e}")
            time.sleep(get_module_exec_seconds())

    module_schedule_thread = threading.Thread(target=module_schedule_worker, daemon=True)
    module_schedule_thread.start()
    logging.info("Started module schedule worker")

    def bulletin_purge_worker():
        while True:
            try:
                reload_sync_peers(interface)
                reload_admin_nodes(interface)
                purge_deleted_bulletins(interface.sync_peers, interface)
                purge_deleted_channels(interface.sync_peers, interface)
            except Exception as e:
                logging.error(f"Error purging deleted records: {e}")
            time.sleep(get_sync_purge_seconds())

    bulletin_purge_thread = threading.Thread(target=bulletin_purge_worker, daemon=True)
    bulletin_purge_thread.start()
    logging.info("Started bulletin and channel purge worker")

    def sync_pending_worker():
        while True:
            try:
                reload_sync_peers(interface)
                reload_admin_nodes(interface)
                sync_pending_records(interface.sync_peers, interface)
            except Exception as e:
                logging.error(f"Error syncing pending records: {e}")
            time.sleep(get_peer_sync_seconds())

    sync_pending_thread = threading.Thread(target=sync_pending_worker, daemon=True)
    sync_pending_thread.start()
    logging.info("Started sync pending worker")

    try:
        while True:
            drain_outbound_user_messages()
            drain_pending_urgent_alerts(interface)
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Shutting down...")
        interface.close()

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        logging.exception("Server failed to start")
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
