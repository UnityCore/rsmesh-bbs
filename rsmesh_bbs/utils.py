import logging
import threading
import time

from meshtastic import BROADCAST_NUM

from .sync_wire import (
    encode_bulletin_sync_message,
    encode_channel_sync_message,
    encode_delete_bulletin_sync_message,
    encode_delete_channel_sync_message,
    encode_delete_mail_sync_message,
    encode_mail_sync_message,
    encode_node_sync_message,
    is_rs_sync_protocol,
    plan_sync_transmit_packets,
)

user_states = {}

MESH_MESSAGE_MAX_SIZE = 200
DISPLAY_FIELD_SEP = "  "


def join_display_fields(*segments):
    return DISPLAY_FIELD_SEP.join(
        "" if segment is None else str(segment) for segment in segments
    )


def bundle_bulletin_read_list(board_name, bulletins, footer=None, max_size=MESH_MESSAGE_MAX_SIZE):
    header = f"{board_name} Bulletins:"
    if footer is None:
        footer = f"Select bulletin number to view from {board_name} or E[X]IT:"
    if bulletins:
        lines = [header] + [f"[{bulletin_id}] {subject}" for bulletin_id, subject, *_ in bulletins]
    else:
        lines = [header, "No bulletins."]

    bundles = []
    current = ""
    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_size:
            current = candidate
            continue
        if current:
            bundles.append(current)
        current = line if len(line) <= max_size else line[:max_size]

    if current:
        bundles.append(current)
    if not bundles:
        bundles = [header]

    last = bundles[-1]
    footer_bundle = f"{last}\n{footer}"
    if len(footer_bundle) <= max_size:
        bundles[-1] = footer_bundle
    else:
        bundles.append(footer)
    return bundles


def bundle_lines_for_mesh(lines, max_size=MESH_MESSAGE_MAX_SIZE):
    bundles = []
    current = ""

    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_size:
            current = candidate
            continue
        if current:
            bundles.append(current)
        current = line if len(line) <= max_size else line[:max_size]

    if current:
        bundles.append(current)

    return bundles


def update_user_state(user_id, state):
    user_states[user_id] = state


def get_user_state(user_id):
    return user_states.get(user_id, None)


def _mesh_ack_handler(interface):
    def handler(packet):
        routing = packet.get("decoded", {}).get("routing", {})
        if routing.get("errorReason", "NONE") != "NONE":
            interface._acknowledgment.receivedNak = True
            return
        if int(packet["from"]) == interface.localNode.nodeNum:
            interface._acknowledgment.receivedImplAck = True
        else:
            interface._acknowledgment.receivedAck = True

    return handler


def _wait_for_mesh_ack(interface):
    ack = interface._acknowledgment
    timeout = interface._timeout
    timeout.reset()
    while time.time() < timeout.expireTime:
        if ack.receivedAck or ack.receivedImplAck:
            ack.reset()
            return True
        if ack.receivedNak:
            ack.reset()
            logging.info("Mesh NAK received; message not acknowledged.")
            return False
        time.sleep(timeout.sleepInterval)
    ack.reset()
    logging.info("Timed out waiting for mesh ACK.")
    return False


MESH_CHUNK_PACE_SECONDS = 2
USER_MESSAGE_PACE_SECONDS = 3


def _message_chunk_count(message, max_size=MESH_MESSAGE_MAX_SIZE):
    if not message:
        return 0
    return (len(message) + max_size - 1) // max_size


def _mesh_send_destination(destination, dest_node_id):
    if destination == BROADCAST_NUM:
        return BROADCAST_NUM
    if dest_node_id is not None:
        return dest_node_id
    return destination


def send_single_message(message, destination, interface, require_ack=False, want_ack=None):
    """Send one mesh text packet without splitting."""
    if len(message) > MESH_MESSAGE_MAX_SIZE:
        logging.error(
            "Mesh message length %s exceeds max packet size %s",
            len(message),
            MESH_MESSAGE_MAX_SIZE,
        )
        return False

    dest_node_id = resolve_destination_node_id(destination, interface)
    mesh_destination = _mesh_send_destination(destination, dest_node_id)
    dest_label = get_destination_display_name(destination, interface)
    if want_ack is None:
        want_ack = require_ack
    ack_handler = _mesh_ack_handler(interface) if require_ack else None
    try:
        if require_ack:
            interface._acknowledgment.reset()
        packet = interface.sendText(
            text=message,
            destinationId=mesh_destination,
            wantAck=want_ack,
            wantResponse=False,
            onResponse=ack_handler,
        )
        logged_message = message.replace('\n', '\\n')
        logging.info(
            f"Sending message to user '{dest_label}' ({dest_node_id or destination}) "
            f"with sendID {packet.id}: \"{logged_message}\""
        )
        if require_ack and not _wait_for_mesh_ack(interface):
            return False
    except Exception as e:
        logging.error(f"REPLY SEND ERROR {e}")
        return False

    time.sleep(MESH_CHUNK_PACE_SECONDS)
    return True


def send_sync_message(message, destination, interface, sync_protocol=None):
    """Send a BBS sync payload, using RS chunk reassembly when required.

    Sync peers (especially TC² BBS nodes) often ingest payloads without returning
    a Meshtastic routing ACK. Request wantAck but do not block on it, same as
    user-facing mesh replies.
    """
    packets = plan_sync_transmit_packets(message, sync_protocol, MESH_MESSAGE_MAX_SIZE)
    if packets is None:
        return False

    for index, packet in enumerate(packets):
        if not send_single_message(
            packet,
            destination,
            interface,
            require_ack=False,
            want_ack=True,
        ):
            return False
        if index < len(packets) - 1:
            time.sleep(MESH_CHUNK_PACE_SECONDS)
    return True


def send_message(message, destination, interface, require_ack=False, want_ack=None):
    max_payload_size = MESH_MESSAGE_MAX_SIZE
    chunks = [
        message[i:i + max_payload_size]
        for i in range(0, len(message), max_payload_size)
    ]

    for index, chunk in enumerate(chunks):
        if not send_single_message(
            chunk,
            destination,
            interface,
            require_ack=require_ack,
            want_ack=want_ack,
        ):
            return False
        if index < len(chunks) - 1:
            time.sleep(MESH_CHUNK_PACE_SECONDS)

    return True


def send_user_messages(messages, destination, interface):
    """Send user-facing messages in order with pacing between each message."""
    if not messages:
        return True

    for index, message in enumerate(messages):
        if not send_message(
            message, destination, interface,
            require_ack=False, want_ack=True,
        ):
            return False
        if index < len(messages) - 1:
            chunk_count = _message_chunk_count(message)
            extra_pace = MESH_CHUNK_PACE_SECONDS * max(0, chunk_count - 1)
            time.sleep(USER_MESSAGE_PACE_SECONDS + extra_pace)

    return True


def send_user_message(message, destination, interface):
    """Send a user-facing reply with brief pacing instead of ACK-wait.

    Mesh ACKs are unreliable for handset delivery ordering and waiting for them
    blocks the pubsub thread, preventing follow-up prompts and new input.
    """
    return send_user_messages([message], destination, interface)


_outbound_lock = threading.Lock()
_outbound_queue = []


def enqueue_user_messages(messages, destination, interface):
    """Queue paced user messages for delivery on the pubsub thread."""
    if not messages or interface is None:
        return
    with _outbound_lock:
        _outbound_queue.append((list(messages), destination, interface))


def drain_outbound_user_messages():
    """Send queued user messages; safe to call from the pubsub or main thread."""
    with _outbound_lock:
        pending = list(_outbound_queue)
        _outbound_queue.clear()
    for messages, destination, interface in pending:
        try:
            send_user_messages(messages, destination, interface)
        except Exception as exc:
            logging.error(
                f"Failed to deliver queued mesh message to {destination}: {exc}",
                exc_info=True,
            )


def _get_node_directory(interface):
    manager = getattr(interface, 'module_manager', None)
    if manager is None:
        return None
    return manager.get_service('node_directory')


def get_node_info(interface, short_name):
    from .node_resolution import resolve_nodes_by_short_name
    return resolve_nodes_by_short_name(short_name, interface)


def get_node_id_from_num(node_num, interface):
    for node_id, node in interface.nodes.items():
        if node['num'] == node_num:
            return node_id
    return None


def resolve_destination_node_id(destination, interface):
    if destination is None:
        return None
    if isinstance(destination, str) and destination.startswith('!'):
        return destination
    if isinstance(destination, str):
        return destination
    return get_node_id_from_num(destination, interface)


def _get_sync_peer_display_name(bbs_node, interface):
    sync_peers = getattr(interface, 'sync_peers', None) or []
    for peer in sync_peers:
        if len(peer) >= 2 and peer[1] == bbs_node:
            bbs_name = peer[2] if len(peer) >= 3 else None
            if bbs_name:
                return bbs_name
    return None


def get_destination_display_name(destination, interface):
    node_id = resolve_destination_node_id(destination, interface)
    if node_id:
        name = get_node_short_name(node_id, interface)
        if name:
            return name
        directory = _get_node_directory(interface)
        if directory is not None:
            record = directory.get_record(node_id)
            if record and record[1]:
                return record[1]
        sync_name = _get_sync_peer_display_name(node_id, interface)
        if sync_name:
            return sync_name
    if destination is not None:
        return str(destination)
    return "Unknown"


def get_node_short_name(node_id, interface):
    node_info = interface.nodes.get(node_id)
    if node_info:
        return node_info['user']['shortName']
    return None


def _touch_sync_peer_last_heard(bbs_node):
    from .db_operations import touch_sync_peer_last_heard
    touch_sync_peer_last_heard(bbs_node)


def sync_peer_bbs_node(peer):
    return peer[1] if len(peer) >= 4 else peer[0]


def sync_peer_protocol(peer):
    return peer[3] if len(peer) >= 4 else peer[2]


PEER_SYNC_FLAG_INDEX = {
    'bulletins': 5,
    'mail': 6,
    'channels': 7,
    'mesh_nodes': 8,
}

PEER_INGEST_FLAG_INDEX = {
    'bulletins': 9,
    'channels': 10,
}


def peer_sync_enabled(peer, record_type):
    index = PEER_SYNC_FLAG_INDEX.get(record_type)
    if index is None:
        return True
    if len(peer) <= index:
        return True
    return (peer[index] or 'Y').strip().upper() == 'Y'


def peer_ingest_enabled(peer, record_type):
    if record_type == 'mail':
        return peer_sync_enabled(peer, 'mail')
    index = PEER_INGEST_FLAG_INDEX.get(record_type)
    if index is None:
        return True
    if len(peer) <= index:
        return True
    return (peer[index] or 'Y').strip().upper() == 'Y'


def peer_accepts_inbound_sync(peer, record_type):
    if peer is None:
        return False
    if record_type == 'mesh_nodes':
        return peer_sync_enabled(peer, 'mesh_nodes')
    return peer_ingest_enabled(peer, record_type)


def get_sync_peer_by_bbs_node(bbs_node, sync_peers=None):
    target = (bbs_node or '').strip()
    if not target:
        return None
    if sync_peers is None:
        return None
    for peer in sync_peers:
        if (peer[1] or '').strip().lower() == target.lower():
            return peer
    return None


def filter_peers_for_record_type(peers, record_type):
    return [peer for peer in peers if peer_sync_enabled(peer, record_type)]


def sync_peer_nodes(sync_peers_or_nodes):
    if not sync_peers_or_nodes:
        return []
    if isinstance(sync_peers_or_nodes[0], tuple):
        return [sync_peer_bbs_node(row) for row in sync_peers_or_nodes]
    return list(sync_peers_or_nodes)


def get_sync_peers_from_interface(interface, fallback_nodes=None):
    sync_peers = getattr(interface, 'sync_peers', None)
    if sync_peers:
        return sync_peers
    if fallback_nodes:
        return [(None, node, None, 'tc2', None, 'Y', 'Y', 'Y', 'N', 'Y', 'Y') for node in fallback_nodes]
    return []


def send_bulletin_to_sync_peers(board, sender_short_name, subject, content, unique_id, sync_peers, interface):
    synced_peers = []
    for peer in sync_peers:
        bbs_node = sync_peer_bbs_node(peer)
        message = encode_bulletin_sync_message(
            sync_peer_protocol(peer),
            board,
            sender_short_name,
            subject,
            content,
            unique_id,
        )
        if send_sync_message(
            message,
            bbs_node,
            interface,
            sync_protocol=sync_peer_protocol(peer),
        ):
            _touch_sync_peer_last_heard(bbs_node)
            synced_peers.append(peer)
        else:
            logging.warning(f"Bulletin sync to {bbs_node} failed.")
    return synced_peers


def send_mail_to_bbs_nodes(
    sender_id,
    sender_short_name,
    recipient_id,
    recipient_short_name,
    subject,
    content,
    unique_id,
    sync_peers,
    interface,
):
    logging.info(
        f"SERVER SYNC: Syncing new mail message {subject} sent from {sender_short_name} to other BBS systems."
    )
    synced_peers = []
    for peer in sync_peers:
        node_id = sync_peer_bbs_node(peer)
        message = encode_mail_sync_message(
            sync_peer_protocol(peer),
            sender_id,
            sender_short_name,
            recipient_id,
            recipient_short_name,
            subject,
            content,
            unique_id,
        )
        if send_sync_message(
            message,
            node_id,
            interface,
            sync_protocol=sync_peer_protocol(peer),
        ):
            _touch_sync_peer_last_heard(node_id)
            synced_peers.append(peer)
        else:
            logging.warning(f"Mail sync to {node_id} failed.")
    return synced_peers


def send_mesh_node_to_peer(node_id, short_name, long_name, last_heard, peer, interface):
    message = encode_node_sync_message(
        sync_peer_protocol(peer),
        node_id,
        short_name,
        long_name,
        last_heard,
    )
    bbs_node = sync_peer_bbs_node(peer)
    if send_sync_message(
        message,
        bbs_node,
        interface,
        sync_protocol=sync_peer_protocol(peer),
    ):
        _touch_sync_peer_last_heard(bbs_node)
        return True
    logging.warning(f"Mesh node sync to {bbs_node} failed.")
    return False


def send_delete_bulletin_to_sync_peers(bulletin_id, unique_id, sync_peers, interface):
    all_ok = True
    for peer in sync_peers:
        bbs_node = sync_peer_bbs_node(peer)
        message = encode_delete_bulletin_sync_message(
            sync_peer_protocol(peer),
            bulletin_id,
            unique_id,
        )
        if send_sync_message(
            message,
            bbs_node,
            interface,
            sync_protocol=sync_peer_protocol(peer),
        ):
            _touch_sync_peer_last_heard(bbs_node)
        else:
            all_ok = False
            logging.warning(f"Delete bulletin sync to {bbs_node} failed.")
    return all_ok


def send_delete_mail_to_bbs_nodes(unique_id, sync_peers, interface):
    logging.info(f"SERVER SYNC: Sending delete mail sync message with unique_id: {unique_id}")
    all_ok = True
    for peer in sync_peers:
        node_id = sync_peer_bbs_node(peer)
        message = encode_delete_mail_sync_message(sync_peer_protocol(peer), unique_id)
        if send_sync_message(
            message,
            node_id,
            interface,
            sync_protocol=sync_peer_protocol(peer),
        ):
            _touch_sync_peer_last_heard(node_id)
        else:
            all_ok = False
            logging.warning(f"Delete mail sync to {node_id} failed.")
    return all_ok


def send_delete_channel_to_sync_peers(unique_id, sync_peers, interface):
    logging.info(f"SERVER SYNC: Sending delete channel sync message with unique_id: {unique_id}")
    all_ok = True
    sent = False
    for peer in sync_peers:
        if not is_rs_sync_protocol(sync_peer_protocol(peer)):
            continue
        bbs_node = sync_peer_bbs_node(peer)
        sent = True
        message = encode_delete_channel_sync_message(sync_peer_protocol(peer), unique_id)
        if send_sync_message(
            message,
            bbs_node,
            interface,
            sync_protocol=sync_peer_protocol(peer),
        ):
            _touch_sync_peer_last_heard(bbs_node)
        else:
            all_ok = False
            logging.warning(f"Delete channel sync to {bbs_node} failed.")
    if not sent:
        return True
    return all_ok


def send_channel_to_bbs_nodes(name, psk, sync_peers, interface, unique_id=None):
    synced_peers = []
    for peer in sync_peers:
        bbs_node = sync_peer_bbs_node(peer)
        message = encode_channel_sync_message(sync_peer_protocol(peer), name, psk, unique_id)
        if send_sync_message(
            message,
            bbs_node,
            interface,
            sync_protocol=sync_peer_protocol(peer),
        ):
            _touch_sync_peer_last_heard(bbs_node)
            synced_peers.append(peer)
        else:
            logging.warning(f"Channel sync to {bbs_node} failed.")
    return synced_peers
