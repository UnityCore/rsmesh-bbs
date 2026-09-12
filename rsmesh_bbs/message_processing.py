import logging

from .command_handlers import (
    dispatch_main_menu_key, handle_help_command,
    handle_mail_menu_steps, handle_modules_steps,
    handle_bb_steps, handle_mail_steps,
    handle_bulletin_delete_steps,
    handle_channel_directory_steps,
)
from .db_operations import (
    add_bulletin, add_mail, delete_bulletin_by_sync_identifier, delete_mail, delete_mail_from_sync,
    get_db_connection,
    add_channel, reload_sync_peers, reload_admin_nodes, get_sync_protocol_for_peer,
    ingest_mesh_node_sync, mark_channel_for_reconcile_by_sync,
)
from .module_sync import CORE_SYNC_PREFIXES, decode_module_rs_payload
from .sync_wire import (
    RS_CHUNK_TYPE,
    SyncChunkAssembler,
    decode_rs_sync_message,
    is_rs_sync_protocol,
    parse_rs_chunk_payload,
    parse_rs_envelope,
)
from .utils import (
    get_user_state, get_node_short_name, get_node_id_from_num, send_message,
    get_sync_peer_by_bbs_node, peer_accepts_inbound_sync, drain_outbound_user_messages,
)
from .node_resolution import is_hex_node_id, record_mesh_node_from_interface, record_mesh_node_from_packet

def _main_menu_keys():
    from .mesh_ui import get_main_menu_keys

    return {key.lower() for key in get_main_menu_keys()}

bulletin_menu_handlers = {
    "g": lambda sender_id, interface: handle_bb_steps(sender_id, '0', 1, {'board': 'General'}, interface, None),
    "i": lambda sender_id, interface: handle_bb_steps(sender_id, '1', 1, {'board': 'Info'}, interface, None),
    "n": lambda sender_id, interface: handle_bb_steps(sender_id, '2', 1, {'board': 'News'}, interface, None),
    "u": lambda sender_id, interface: handle_bb_steps(sender_id, '3', 1, {'board': 'Urgent'}, interface, None),
    "x": handle_help_command
}

board_action_handlers = {
    "r": lambda sender_id, interface, state: handle_bb_steps(sender_id, 'r', 2, state, interface, None),
    "p": lambda sender_id, interface, state: handle_bb_steps(sender_id, 'p', 2, state, interface, None),
    "d": lambda sender_id, interface, state: handle_bb_steps(sender_id, 'd', 2, state, interface, None),
    "x": handle_help_command
}

_sync_chunk_assembler = SyncChunkAssembler()


def _parse_bulletin_sync(message):
    parts = message.split("|")
    if len(parts) < 6 or parts[0] != "BULLETIN":
        raise ValueError("Invalid BULLETIN sync message format")

    board = parts[1]
    sender_short_name = parts[2]
    subject = parts[3]
    unique_id = parts[-1]
    content = "|".join(parts[4:-1])
    return board, sender_short_name, subject, content, unique_id


def _parse_mail_sync(message):
    body, unique_id = message.rsplit("|", 1)
    parts = body.split("|")
    if len(parts) < 6:
        raise ValueError("Invalid MAIL sync message format")
    mail_sender_id = parts[1]
    sender_short_name = parts[2]
    recipient_ref = parts[3]
    subject = parts[4]
    content = "|".join(parts[5:])
    return mail_sender_id, sender_short_name, recipient_ref, None, subject, content, unique_id


def _mail_sync_fields(recipient_ref, recipient_short_name):
    recipient_ref = (recipient_ref or "").strip()
    recipient_short_name = (recipient_short_name or "").strip()
    if is_hex_node_id(recipient_ref):
        return recipient_ref, recipient_short_name
    if recipient_ref and not recipient_short_name:
        recipient_short_name = recipient_ref
    return None, recipient_short_name or recipient_ref


def _parse_channel_sync(message):
    parts = message.split("|", 2)
    if len(parts) < 3 or parts[0] != "CHANNEL":
        raise ValueError("Invalid CHANNEL sync message format")
    return parts[1], parts[2], None


def _legacy_pipe_sync_rejected(sender_node_id, record_type):
    protocol = get_sync_protocol_for_peer(sender_node_id) or 'tc2'
    if is_rs_sync_protocol(protocol):
        logging.info(
            f"Ignoring legacy pipe {record_type} sync from RS peer {sender_node_id}; "
            f"use RS wire format."
        )
        return True
    return False


def _module_sync_manager(interface):
    return getattr(interface, "module_manager", None)


def _inbound_module_sync_allowed(sender_node_id, interface, registration):
    manager = _module_sync_manager(interface)
    if manager is None or not manager.is_module_sync_enabled(registration.module_id):
        logging.info(
            "Ignoring inbound %s sync from %s; module %s disabled.",
            registration.record_type,
            sender_node_id,
            registration.module_id,
        )
        return False
    return _inbound_sync_allowed(sender_node_id, interface, registration.record_type)


def _dispatch_module_rs_sync(message, interface, sender_node_id):
    manager = _module_sync_manager(interface)
    if manager is None:
        return False
    wire_version, msg_type, fields = decode_module_rs_payload(message)
    registration = manager.lookup_sync_by_wire_type(msg_type)
    if registration is None or registration.on_inbound_rs is None:
        return False
    if not _inbound_module_sync_allowed(sender_node_id, interface, registration):
        return False
    from .db_operations import note_rs_wire_version

    note_rs_wire_version(sender_node_id, wire_version)
    registration.on_inbound_rs(msg_type, fields, sender_node_id, interface)
    return True


def _inbound_sync_allowed(sender_node_id, interface, record_type):
    from .core_services import is_core_sync_enabled

    if not is_core_sync_enabled(record_type):
        logging.info(
            f"Ignoring inbound {record_type} sync from {sender_node_id}; "
            f"core service disabled locally."
        )
        return False
    peer = get_sync_peer_by_bbs_node(sender_node_id, getattr(interface, 'sync_peers', None))
    if not peer_accepts_inbound_sync(peer, record_type, interface):
        logging.info(
            f"Ignoring inbound {record_type} sync from {sender_node_id}; "
            f"ingest disabled for this peer."
        )
        return False
    return True


def _sync_ingest_bulletin_tc2(board, sender_short_name, subject, content, unique_id, interface):
    add_bulletin(
        board, sender_short_name, subject, content, [], interface,
        unique_id=unique_id, from_sync=True,
    )
    from .urgent_alerts import maybe_send_urgent_alert_from_sync

    maybe_send_urgent_alert_from_sync(board, sender_short_name, subject, interface)


def _sync_ingest_mail(
    mail_sender_id,
    sender_short_name,
    recipient_ref,
    recipient_short_name,
    subject,
    content,
    unique_id,
    interface,
):
    recipient_id, recipient_short_name = _mail_sync_fields(recipient_ref, recipient_short_name)
    add_mail(
        mail_sender_id, sender_short_name, recipient_id, subject, content,
        [], interface, unique_id=unique_id, from_sync=True,
        recipient_short_name=recipient_short_name,
    )


def _process_rs_sync_message(sender_id, message, interface, sender_node_id):
    manager = _module_sync_manager(interface)
    if manager is not None:
        _, msg_type, _payload = parse_rs_envelope(message)
        if manager.lookup_sync_by_wire_type(msg_type) is not None:
            _dispatch_module_rs_sync(message, interface, sender_node_id)
            return

    msg_type, fields = decode_rs_sync_message(message, sender_node_id)
    if msg_type == "BULLETIN":
        if not _inbound_sync_allowed(sender_node_id, interface, 'bulletins'):
            return
        from .db_operations import ingest_bulletin_from_rsv1_sync

        ingest_bulletin_from_rsv1_sync(
            fields["board"],
            fields["sender_short_name"],
            fields["subject"],
            fields["content"],
            fields["unique_id"],
            pinned=fields.get("pinned", "N"),
            interface=interface,
        )
    elif msg_type == "MAIL":
        if not _inbound_sync_allowed(sender_node_id, interface, 'mail'):
            return
        _sync_ingest_mail(
            fields["mail_sender_id"],
            fields["sender_short_name"],
            fields["recipient_id"],
            fields["recipient_short_name"],
            fields["subject"],
            fields["content"],
            fields["unique_id"],
            interface,
        )
    elif msg_type == "NODE":
        if not _inbound_sync_allowed(sender_node_id, interface, 'mesh_nodes'):
            return
        if not is_rs_sync_protocol(get_sync_protocol_for_peer(sender_node_id) or 'tc2'):
            logging.info(f"Ignoring NODE sync from non-RS peer {sender_node_id}.")
            return
        ingest_mesh_node_sync(
            fields["node_id"],
            fields["short_name"],
            fields["long_name"],
            fields["last_heard"],
            sender_node_id=sender_node_id,
        )
    elif msg_type == "DELETE_BULLETIN":
        if not _inbound_sync_allowed(sender_node_id, interface, 'bulletins'):
            return
        delete_bulletin_by_sync_identifier(fields["identifier"], sender_node_id)
    elif msg_type == "DELETE_MAIL":
        if not _inbound_sync_allowed(sender_node_id, interface, 'mail'):
            return
        unique_id = fields["unique_id"]
        logging.info(f"Processing delete mail with unique_id: {unique_id}")
        delete_mail_from_sync(unique_id, [], interface)
    elif msg_type == "CHANNEL":
        if not _inbound_sync_allowed(sender_node_id, interface, 'channels'):
            return
        add_channel(
            fields["channel_name"],
            fields["channel_psk"],
            from_sync=True,
            unique_id=fields["unique_id"],
        )
    elif msg_type == "DELETE_CHANNEL":
        if not _inbound_sync_allowed(sender_node_id, interface, 'channels'):
            return
        if not is_rs_sync_protocol(get_sync_protocol_for_peer(sender_node_id) or 'tc2'):
            logging.info(
                f"Ignoring DELETE_CHANNEL from non-RS peer {sender_node_id}."
            )
            return
        mark_channel_for_reconcile_by_sync(fields["unique_id"], sender_node_id)
    else:
        raise ValueError(f"Unsupported RS sync message type: {msg_type}")


def _process_sync_message(sender_id, message, interface, sender_node_id):
    try:
        if message.startswith("RS|"):
            wire_version, msg_type, payload = parse_rs_envelope(message)
            if msg_type == RS_CHUNK_TYPE:
                from .db_operations import note_rs_wire_version
                note_rs_wire_version(sender_node_id, wire_version)
                transfer_id, index, total, chunk_payload = parse_rs_chunk_payload(payload)
                complete_message = _sync_chunk_assembler.add_chunk(
                    sender_node_id,
                    transfer_id,
                    index,
                    total,
                    chunk_payload,
                )
                if complete_message:
                    _process_sync_message(
                        sender_id, complete_message, interface, sender_node_id
                    )
                return
            _process_rs_sync_message(sender_id, message, interface, sender_node_id)
            return
        if message.startswith("BULLETIN|"):
            if _legacy_pipe_sync_rejected(sender_node_id, "BULLETIN"):
                return
            if not _inbound_sync_allowed(sender_node_id, interface, 'bulletins'):
                return
            board, sender_short_name, subject, content, unique_id = _parse_bulletin_sync(message)
            _sync_ingest_bulletin_tc2(
                board, sender_short_name, subject, content, unique_id, interface,
            )
        elif message.startswith("MAIL|"):
            if _legacy_pipe_sync_rejected(sender_node_id, "MAIL"):
                return
            if not _inbound_sync_allowed(sender_node_id, interface, 'mail'):
                return
            mail_sender_id, sender_short_name, recipient_ref, recipient_short_name, subject, content, unique_id = (
                _parse_mail_sync(message)
            )
            _sync_ingest_mail(
                mail_sender_id, sender_short_name, recipient_ref, recipient_short_name,
                subject, content, unique_id, interface,
            )
        elif message.startswith("DELETE_BULLETIN|"):
            if _legacy_pipe_sync_rejected(sender_node_id, "DELETE_BULLETIN"):
                return
            if not _inbound_sync_allowed(sender_node_id, interface, 'bulletins'):
                return
            identifier = message.split("|", 1)[1]
            delete_bulletin_by_sync_identifier(identifier, sender_node_id)
        elif message.startswith("DELETE_MAIL|"):
            if _legacy_pipe_sync_rejected(sender_node_id, "DELETE_MAIL"):
                return
            if not _inbound_sync_allowed(sender_node_id, interface, 'mail'):
                return
            unique_id = message.split("|", 1)[1]
            logging.info(f"Processing delete mail with unique_id: {unique_id}")
            delete_mail_from_sync(unique_id, [], interface)
        elif message.startswith("CHANNEL|"):
            if _legacy_pipe_sync_rejected(sender_node_id, "CHANNEL"):
                return
            if not _inbound_sync_allowed(sender_node_id, interface, 'channels'):
                return
            channel_name, channel_psk, unique_id = _parse_channel_sync(message)
            add_channel(
                channel_name, channel_psk, from_sync=True, unique_id=unique_id
            )
    except (ValueError, IndexError) as e:
        logging.error(f"Error parsing sync message: {e}")


def _handle_user_message(sender_id, message, interface):
    state = get_user_state(sender_id)
    message_lower = message.lower().strip()
    bbs_nodes = interface.bbs_nodes

    if len(message_lower) == 2 and message_lower[1] == 'x':
        message_lower = message_lower[0]

    if message_lower == 'x':
        handle_help_command(sender_id, interface)
        return

    if state:
        command = state['command']
        step = state['step']

        if command == 'MAIL':
            handle_mail_steps(sender_id, message, step, state, interface, bbs_nodes)
            return
        elif command == 'MAIL_MENU':
            handle_mail_menu_steps(sender_id, message, step, interface)
            return
        elif command == 'MODULES':
            handle_modules_steps(sender_id, message, step, interface)
            return
        elif command == 'MODULE':
            from .module_loader import MODULE_RESULT_EXIT
            manager = getattr(interface, 'module_manager', None)
            if manager is None:
                handle_help_command(sender_id, interface)
                return
            result = manager.on_module_message(state['module_id'], sender_id, message, interface)
            if result == MODULE_RESULT_EXIT:
                handle_help_command(sender_id, interface)
            return
        elif command == 'CHANNEL_DIRECTORY':
            handle_channel_directory_steps(sender_id, message, step, state, interface, bbs_nodes)
            return
        elif command == 'BULLETIN_POST':
            handle_bb_steps(sender_id, message, 4, state, interface, bbs_nodes)
            return
        elif command == 'BULLETIN_POST_CONTENT':
            handle_bb_steps(sender_id, message, 5, state, interface, bbs_nodes)
            return
        elif command == 'BULLETIN_READ':
            handle_bb_steps(sender_id, message, 3, state, interface, bbs_nodes)
            return
        elif command == 'BULLETIN_DELETE':
            handle_bulletin_delete_steps(sender_id, message, step, state, interface, bbs_nodes)
            return

    on_main_menu = not state or state.get('command') == 'MAIN_MENU'
    if on_main_menu:
        if message_lower in _main_menu_keys():
            dispatch_main_menu_key(sender_id, interface, message_lower)
        else:
            handle_help_command(sender_id, interface)
        return

    if state and state['command'] == 'BULLETIN_MENU':
        handlers = bulletin_menu_handlers
    elif state and state['command'] == 'BULLETIN_ACTION':
        handlers = board_action_handlers
    else:
        handlers = {}

    if message_lower in handlers:
        if state and state['command'] == 'BULLETIN_ACTION':
            handlers[message_lower](sender_id, interface, state)
        else:
            handlers[message_lower](sender_id, interface)
    else:
        handle_help_command(sender_id, interface)


def process_message(sender_id, message, interface, is_sync_message=False, sender_node_id=None):
    reload_sync_peers(interface)
    reload_admin_nodes(interface)
    if is_sync_message:
        _process_sync_message(sender_id, message, interface, sender_node_id)
        return

    try:
        _handle_user_message(sender_id, message, interface)
    except Exception as e:
        logging.error(f"Error handling user message from {sender_id}: {e}", exc_info=True)


def on_receive(packet, interface):
    try:
        drain_outbound_user_messages()
        record_mesh_node_from_packet(packet, interface)
        if 'decoded' in packet and packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP':
            message_bytes = packet['decoded']['payload']
            message_string = message_bytes.decode('utf-8')
            sender_id = packet['from']
            to_id = packet.get('to')
            sender_node_id = packet['fromId']

            sender_short_name = get_node_short_name(sender_node_id, interface)
            receiver_short_name = get_node_short_name(get_node_id_from_num(to_id, interface),
                                                      interface) if to_id else "Group Chat"
            logging.info(f"Received message from user '{sender_short_name}' ({sender_node_id}) to {receiver_short_name}: {message_string}")

            bbs_nodes = interface.bbs_nodes
            is_sync_message = any(
                message_string.startswith(prefix)
                for prefix in CORE_SYNC_PREFIXES
            )

            if sender_node_id in bbs_nodes:
                if is_sync_message:
                    process_message(
                        sender_id, message_string, interface,
                        is_sync_message=True, sender_node_id=sender_node_id
                    )
                else:
                    logging.info("Ignoring non-sync message from known BBS node")
            elif to_id is not None and to_id != 0 and to_id != 255 and to_id == interface.myInfo.my_node_num:
                process_message(sender_id, message_string, interface, is_sync_message=False)
            else:
                logging.info("Ignoring message sent to group chat or from unknown node")
    except Exception as e:
        logging.error(f"Error processing packet: {e}", exc_info=True)

def get_recipient_id_by_mail(unique_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT recipient, recipient_short_name FROM mail WHERE unique_id = ?",
        (unique_id,),
    )
    result = c.fetchone()
    if result:
        recipient, recipient_short_name = result
        return recipient or recipient_short_name
    return None
