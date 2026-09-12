import logging
import time

from .config_init import get_board_name
from .db_operations import (
    add_bulletin, add_mail, delete_mail, mark_bulletin_deleted,
    get_mesh_bulletin_content, get_mesh_bulletins,
    get_mail, get_mail_content,
    add_channel, get_channels, get_sender_id_by_mail_id
)
from .utils import (
    get_node_id_from_num, get_node_info,
    get_node_short_name, send_message, send_user_message, send_user_messages,
    update_user_state, bundle_bulletin_read_list,
)
from .mesh_ui import MAIL_SUBMENU_TEXT, load_main_menu_body
from .node_resolution import is_hex_node_id

EXIT_PROMPT = "E[X]IT"


def _parse_int(message):
    try:
        return int(message.strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _show_mail_inbox(sender_id, interface, prefix_messages=None, return_to_mail_menu=False):
    sender_node_id = get_node_id_from_num(sender_id, interface)
    mail = get_mail(sender_node_id, interface)
    if mail:
        messages = list(prefix_messages or []) + [
            with_exit_prompt(f"{len(mail)} message(s). Select message number to read:"),
        ]
        for msg in mail:
            mail_id, sender_short_name, subject, date, _unique_id, read_flag = msg
            header = f"-{mail_id}-"
            if (read_flag or "N").upper() == "N":
                header += " *NEW*"
            messages.append(
                f"{header}\nDate: {date}\nFrom: {sender_short_name}\nSubject: {subject}"
            )
        send_user_messages(messages, sender_id, interface)
        update_user_state(sender_id, {'command': 'MAIL', 'step': 2})
    else:
        empty_notice = list(prefix_messages or [])
        empty_notice.append("No messages.")
        if return_to_mail_menu:
            handle_mail_menu_command(sender_id, interface, prefix_messages=empty_notice)
        elif prefix_messages:
            send_user_messages(empty_notice, sender_id, interface)
            update_user_state(sender_id, None)
        else:
            send_user_message("No messages.", sender_id, interface)
            update_user_state(sender_id, None)


def _send_bulletin_delete_prompt(sender_id, interface, board_name, prefix_messages=None):
    bulletins = get_mesh_bulletins(board_name)
    if not bulletins:
        send_message(f"No bulletins in {board_name}.", sender_id, interface)
        handle_help_command(sender_id, interface)
        return
    delete_footer = f"Select bulletin number to delete from {board_name} or E[X]IT:"
    bundles = bundle_bulletin_read_list(board_name, bulletins, footer=delete_footer)
    messages = list(prefix_messages or []) + bundles
    send_user_messages(messages, sender_id, interface)
    update_user_state(sender_id, {'command': 'BULLETIN_DELETE', 'step': 1, 'board': board_name})


def _show_channel_pick_list(sender_id, interface):
    channels = get_channels()
    if not channels:
        send_message("No channels available.", sender_id, interface)
        handle_channel_directory_command(sender_id, interface)
        return
    response = with_exit_prompt(
        "Select channel number:\n" + "\n".join(
            [f"[{i}] {channel[0]}" for i, channel in enumerate(channels)]
        )
    )
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 2})


def _show_mail_node_picker(sender_id, interface, nodes, prefix_messages=None):
    messages = list(prefix_messages or []) + [
        with_exit_prompt("Multiple nodes with short name. Select node to leave a message for:"),
    ]
    for i, node in enumerate(nodes):
        messages.append(f"[{i}] {node['longName']}")
    send_user_messages(messages, sender_id, interface)
    update_user_state(sender_id, {'command': 'MAIL', 'step': 6, 'nodes': nodes})


def with_exit_prompt(menu_text, include_exit=True):
    """Append an exit prompt when exit is available and not already shown."""
    if not include_exit:
        return menu_text
    if "E[X]IT" in menu_text.upper():
        return menu_text
    if menu_text and not menu_text.endswith('\n'):
        menu_text += '\n'
    return menu_text + EXIT_PROMPT


def handle_help_command(sender_id, interface, prefix_messages=None):
    update_user_state(sender_id, {'command': 'MAIN_MENU', 'step': 1})
    mail = get_mail(get_node_id_from_num(sender_id, interface), interface)
    board_name = get_board_name()
    title = f"= {board_name} : {len(mail)} Msg(s) ="
    response = f"{title}\n{load_main_menu_body(board_name=board_name)}"
    messages = list(prefix_messages or []) + [response]
    send_user_messages(messages, sender_id, interface)

def _send_bulletin_read_prompt(sender_id, interface, board_name, prefix_messages=None):
    bulletins = get_mesh_bulletins(board_name)
    bundles = bundle_bulletin_read_list(board_name, bulletins)
    if not bundles:
        handle_help_command(sender_id, interface)
        return
    messages = list(prefix_messages or []) + bundles
    send_user_messages(messages, sender_id, interface)
    update_user_state(sender_id, {'command': 'BULLETIN_READ', 'step': 3, 'board': board_name})

def get_node_name(node_id, interface):
    node_info = interface.nodes.get(node_id)
    if node_info:
        return node_info['user']['longName']
    return f"Node {node_id}"


def is_sysadmin(sender_id, interface):
    node_id = get_node_id_from_num(sender_id, interface)
    admin_nodes = getattr(interface, 'admin_nodes', None) or []
    return bool(node_id and node_id in admin_nodes)


def _bulletin_board_actions(sender_id, interface):
    actions = "[R]ead  [P]ost"
    if is_sysadmin(sender_id, interface):
        actions += "  [D]elete"
    return actions


def handle_bulletin_delete_steps(sender_id, message, step, state, interface, bbs_nodes):
    if step == 1:
        if not is_sysadmin(sender_id, interface):
            send_message("You do not have permission to delete bulletins.", sender_id, interface)
            update_user_state(sender_id, None)
            return

        board_name = state['board']
        bulletin_id = _parse_int(message)
        if bulletin_id is None:
            _send_bulletin_delete_prompt(
                sender_id, interface, board_name,
                prefix_messages=["Invalid bulletin number."],
            )
            return

        bulletin = get_mesh_bulletin_content(bulletin_id, board_name)
        if bulletin is None:
            _send_bulletin_delete_prompt(
                sender_id, interface, board_name,
                prefix_messages=["Bulletin not found."],
            )
            return

        if not mark_bulletin_deleted(bulletin_id):
            _send_bulletin_delete_prompt(
                sender_id, interface, board_name,
                prefix_messages=["Bulletin not found."],
            )
            return

        handle_help_command(sender_id, interface, prefix_messages=["Bulletin deleted."])


def _mail_returns_to_submenu():
    from .core_services import is_mail_commands_on_main_menu

    return not is_mail_commands_on_main_menu()


def handle_read_mail_command(sender_id, interface):
    _show_mail_inbox(sender_id, interface, return_to_mail_menu=_mail_returns_to_submenu())


def handle_send_mail_command(sender_id, interface):
    send_user_message("Short Name of the node to message?", sender_id, interface)
    update_user_state(sender_id, {'command': 'MAIL', 'step': 3})


def handle_mail_menu_command(sender_id, interface, prefix_messages=None):
    response = with_exit_prompt(MAIL_SUBMENU_TEXT)
    messages = list(prefix_messages or []) + [response]
    send_user_messages(messages, sender_id, interface)
    update_user_state(sender_id, {'command': 'MAIL_MENU', 'step': 1})


def handle_mail_menu_steps(sender_id, message, step, interface):
    message = message.lower().strip()
    if len(message) == 2 and message[1] == 'x':
        message = message[0]
    if message == 'x':
        handle_help_command(sender_id, interface)
        return
    if step != 1:
        handle_help_command(sender_id, interface)
        return
    if message == 'r':
        handle_read_mail_command(sender_id, interface)
    elif message == 's':
        handle_send_mail_command(sender_id, interface)
    else:
        handle_mail_menu_command(sender_id, interface, prefix_messages=["Invalid option."])


def handle_bulletin_command(sender_id, interface):
    response = with_exit_prompt("= Bulletin Menu =\nSelect Board:\n[G]eneral  [I]nfo  [N]ews  [U]rgent")
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'BULLETIN_MENU', 'step': 1})


def handle_exit_command(sender_id, interface):
    send_message("Type 'HELP' for a list of commands.", sender_id, interface)
    update_user_state(sender_id, None)


def handle_modules_command(sender_id, interface):
    from .mesh_ui import should_show_modules_entry

    manager = getattr(interface, 'module_manager', None)
    if manager is None or not should_show_modules_entry():
        send_message("Modules are not available.", sender_id, interface)
        handle_help_command(sender_id, interface)
        return
    send_message(manager.build_modules_menu_text(), sender_id, interface)
    update_user_state(sender_id, {'command': 'MODULES', 'step': 1})


def handle_modules_steps(sender_id, message, step, interface):
    message = message.lower().strip()
    if len(message) == 2 and message[1] == 'x':
        message = message[0]
    if step != 1:
        handle_help_command(sender_id, interface)
        return
    if message == 'x':
        handle_help_command(sender_id, interface)
        return
    manager = getattr(interface, 'module_manager', None)
    if manager is None:
        handle_help_command(sender_id, interface)
        return
    entry = manager.get_by_menu_option(message)
    if not entry:
        send_message("Invalid module selection.", sender_id, interface)
        handle_modules_command(sender_id, interface)
        return
    row, _instance = entry
    if not manager.on_module_enter(row[0], sender_id, interface):
        send_message("Module is not available.", sender_id, interface)
        handle_modules_command(sender_id, interface)


def handle_bb_steps(sender_id, message, step, state, interface, bbs_nodes):
    boards = {0: "General", 1: "Info", 2: "News", 3: "Urgent"}
    if step == 1:
        if message.lower() == 'e':
            handle_help_command(sender_id, interface)
            return
        board_name = boards.get(_parse_int(message))
        if board_name is None:
            send_message("Invalid board selection.", sender_id, interface)
            handle_help_command(sender_id, interface)
            return
        bulletins = get_mesh_bulletins(board_name)
        response = with_exit_prompt(
            f"{board_name} has {len(bulletins)} messages.\n{_bulletin_board_actions(sender_id, interface)}"
        )
        send_message(response, sender_id, interface)
        update_user_state(sender_id, {'command': 'BULLETIN_ACTION', 'step': 2, 'board': board_name})

    elif step == 2:
        board_name = state['board']
        if message.lower() == 'r':
            bulletins = get_mesh_bulletins(board_name)
            if bulletins:
                _send_bulletin_read_prompt(sender_id, interface, board_name)
            else:
                handle_bb_steps(sender_id, 'e', 1, state, interface, bbs_nodes)
        elif message.lower() == 'p':
            if board_name.lower() == 'urgent' and not is_sysadmin(sender_id, interface):
                send_message("You do not have permission to post to this board.", sender_id, interface)
                handle_bb_steps(sender_id, 'e', 1, state, interface, bbs_nodes)
                return
            send_message("Subject of your bulletin? Keep it short.", sender_id, interface)
            update_user_state(sender_id, {'command': 'BULLETIN_POST', 'step': 4, 'board': board_name})
        elif message.lower() == 'd':
            if not is_sysadmin(sender_id, interface):
                send_message("You do not have permission to delete bulletins.", sender_id, interface)
                handle_bb_steps(sender_id, 'e', 1, state, interface, bbs_nodes)
                return
            bulletins = get_mesh_bulletins(board_name)
            if bulletins:
                _send_bulletin_delete_prompt(sender_id, interface, board_name)
            else:
                send_message(f"No bulletins in {board_name}.", sender_id, interface)
                handle_bb_steps(sender_id, 'e', 1, state, interface, bbs_nodes)

    elif step == 3:
        board_name = state['board']
        if message.lower() == 'x':
            handle_help_command(sender_id, interface)
            return
        bulletin_id = _parse_int(message)
        if bulletin_id is None:
            _send_bulletin_read_prompt(
                sender_id, interface, board_name,
                prefix_messages=["Invalid bulletin number."],
            )
            return
        bulletin = get_mesh_bulletin_content(bulletin_id, board_name)
        if bulletin is None:
            _send_bulletin_read_prompt(
                sender_id, interface, board_name,
                prefix_messages=["Bulletin not found."],
            )
            return
        sender_short_name, date, subject, content = bulletin
        bulletin_text = (
            f"From: {sender_short_name}\nDate: {date}\nSubject: {subject}\n"
            f"- - - - - - -\n{content}"
        )
        _send_bulletin_read_prompt(
            sender_id, interface, board_name,
            prefix_messages=[bulletin_text],
        )

    elif step == 4:
        subject = message
        send_message("Send new bulletin. Send a message with END when finished.", sender_id, interface)
        update_user_state(sender_id, {'command': 'BULLETIN_POST_CONTENT', 'step': 5, 'board': state['board'], 'subject': subject, 'content': ''})

    elif step == 5:
        if message.lower() == "end":
            board = state['board']
            subject = state['subject']
            content = state['content']
            node_id = get_node_id_from_num(sender_id, interface)
            node_info = interface.nodes.get(node_id)
            if node_info is None:
                send_message("Error: Unable to retrieve your node information.", sender_id, interface)
                update_user_state(sender_id, None)
                return
            sender_short_name = node_info['user'].get('shortName', f"Node {sender_id}")
            add_bulletin(
                board, sender_short_name, subject, content, bbs_nodes, interface,
                defer_sync=True,
            )
            send_user_messages([
                with_exit_prompt(f"Bulletin '{subject}' posted to {board}."),
            ], sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIN_MENU', 'step': 1})
        else:
            state['content'] += message + "\n"
            update_user_state(sender_id, state)



def handle_mail_steps(sender_id, message, step, state, interface, bbs_nodes):
    message = message.strip()
    if len(message) == 2 and message[1] == 'x':
        message = message[0]

    if step == 2:
        mail_id = _parse_int(message)
        if mail_id is None:
            _show_mail_inbox(
                sender_id, interface,
                prefix_messages=["Invalid message number."],
            )
            return
        try:
            sender_node_id = get_node_id_from_num(sender_id, interface)
            sender, date, subject, content, unique_id = get_mail_content(mail_id, sender_node_id, interface)
            if unique_id is None:
                raise TypeError("mail not found")
            mail_text = f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n{content}"
            send_user_messages([
                mail_text,
                with_exit_prompt("Message command:\n[K]eep  [D]elete  [R]eply"),
            ], sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 4, 'mail_id': mail_id, 'unique_id': unique_id, 'sender': sender, 'subject': subject, 'content': content})
        except TypeError:
            logging.info(f"Node {sender_id} tried to access non-existent message")
            _show_mail_inbox(
                sender_id, interface,
                prefix_messages=["Mail not found."],
            )

    elif step == 3:
        short_name = message.lower()
        nodes = get_node_info(interface, short_name)
        if not nodes:
            send_user_messages([
                "Node not found in database.",
                "Short Name of the node to message?",
            ], sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 3})
        elif len(nodes) == 1:
            recipient_id = nodes[0]['num']
            recipient_short_name = nodes[0]['shortName']
            recipient_name = get_node_name(recipient_id, interface)
            send_user_message(
                f"Subject of message to {recipient_name}?\nKeep it short.",
                sender_id, interface,
            )
            update_user_state(sender_id, {
                'command': 'MAIL', 'step': 5,
                'recipient_id': recipient_id,
                'recipient_short_name': recipient_short_name,
            })
        else:
            _show_mail_node_picker(sender_id, interface, nodes)

    elif step == 4:
        if message.lower() == "d":
            unique_id = state['unique_id']
            sender_node_id = get_node_id_from_num(sender_id, interface)
            delete_mail(unique_id, sender_node_id, bbs_nodes, interface)
            _show_mail_inbox(sender_id, interface, prefix_messages=["Message deleted."])
        elif message.lower() == "r":
            sender = state['sender']
            send_user_message(
                f"Send reply to {sender}, followed by a message with END",
                sender_id, interface,
            )
            update_user_state(sender_id, {'command': 'MAIL', 'step': 7, 'reply_to_mail_id': state['mail_id'], 'subject': f"Re: {state['subject']}", 'content': ''})
        else:
            _show_mail_inbox(sender_id, interface, prefix_messages=["Message kept."])

    elif step == 5:
        subject = message
        send_user_message(
            "Send message. Send in multiple messages if too long for one.\n"
            "Send message with END when finished.",
            sender_id, interface,
        )
        update_user_state(sender_id, {'command': 'MAIL', 'step': 7, 'recipient_id': state['recipient_id'], 'subject': subject, 'content': ''})

    elif step == 6:
        selected_node_index = _parse_int(message)
        nodes = state.get('nodes') or []
        if selected_node_index is None or not (0 <= selected_node_index < len(nodes)):
            _show_mail_node_picker(
                sender_id, interface, nodes,
                prefix_messages=["Invalid selection."],
            )
            return
        selected_node = nodes[selected_node_index]
        recipient_id = selected_node['num']
        recipient_short_name = selected_node['shortName']
        recipient_name = get_node_name(recipient_id, interface)
        send_user_message(
            f"Subject of message to {recipient_name}?\nKeep it short.",
            sender_id, interface,
        )
        update_user_state(sender_id, {
            'command': 'MAIL', 'step': 5,
            'recipient_id': recipient_id,
            'recipient_short_name': recipient_short_name,
        })

    elif step == 7:
        if message.lower() == "end":
            if 'reply_to_mail_id' in state:
                recipient_id = get_sender_id_by_mail_id(state['reply_to_mail_id'])
                if recipient_id is None:
                    send_user_message(
                        "Unable to send reply; original message not found.",
                        sender_id, interface,
                    )
                    update_user_state(sender_id, None)
                    return
            else:
                recipient_id = state.get('recipient_id')
                if recipient_id is None:
                    send_user_message(
                        "Unable to send mail; recipient not found.",
                        sender_id, interface,
                    )
                    update_user_state(sender_id, None)
                    return

            subject = state['subject']
            content = state['content']
            recipient_name = get_node_name(recipient_id, interface)
            sender_node_id = get_node_id_from_num(sender_id, interface)
            sender_short_name = get_node_short_name(sender_node_id, interface)
            recipient_short_name = state.get('recipient_short_name')

            _, final_recipient_id = add_mail(
                sender_node_id, sender_short_name, recipient_id, subject, content,
                bbs_nodes, interface, defer_sync=True,
                recipient_short_name=recipient_short_name,
            )
            return_to_inbox = 'reply_to_mail_id' in state
            update_user_state(sender_id, {
                'command': 'MAIL', 'step': 8, 'return_to_inbox': return_to_inbox,
            })

            send_user_messages([
                f"Mail has been posted to the mailbox of {recipient_name}.",
                "Send another message? [Y]es / [N]o",
            ], sender_id, interface)

            notification_message = (
                f"New mail from {sender_short_name}. Type HELP and press R to read mail."
            )
            try:
                if is_hex_node_id(final_recipient_id):
                    send_message(notification_message, final_recipient_id, interface)
            except Exception as e:
                logging.error(
                    f"Failed to notify mail recipient {final_recipient_id}: {e}",
                    exc_info=True,
                )
        else:
            state['content'] += message + "\n"
            update_user_state(sender_id, state)

    elif step == 8:
        if message.lower() == "y":
            handle_send_mail_command(sender_id, interface)
        elif state.get('return_to_inbox'):
            _show_mail_inbox(sender_id, interface)
        else:
            handle_help_command(sender_id, interface)


def _channel_directory_menu():
    return with_exit_prompt("= Channel Directory =\nSelect option:\n[V]iew  [P]ost")


def dispatch_main_menu_key(sender_id, interface, menu_key):
    """Route a main-menu key to core service handlers or a module override."""
    from .core_services import (
        MAIN_MENU_HANDLER_KEYS,
        is_core_mail_enabled,
        is_core_service_enabled,
        is_mail_commands_on_main_menu,
    )

    menu_key = (menu_key or "").lower()
    if is_core_mail_enabled() and is_mail_commands_on_main_menu():
        if menu_key == "r":
            handle_read_mail_command(sender_id, interface)
            return
        if menu_key == "s":
            handle_send_mail_command(sender_id, interface)
            return
    manager = getattr(interface, "module_manager", None)
    module_entry = manager.get_by_menu_option(menu_key) if manager else None
    if module_entry:
        row, _instance = module_entry
        main_menu_visible = row[6] if len(row) > 6 else "N"
        if main_menu_visible == "Y":
            if manager.on_module_enter(row[0], sender_id, interface):
                return
            handle_help_command(sender_id, interface)
            return

    core_handlers = {
        "b": handle_bulletin_command,
        "c": handle_channel_directory_command,
        "m": handle_mail_menu_command,
        "o": handle_modules_command,
        "x": handle_help_command,
    }
    handler = core_handlers.get(menu_key)
    if handler is None:
        handle_help_command(sender_id, interface)
        return

    cfg_key = MAIN_MENU_HANDLER_KEYS.get(menu_key)
    if (
        menu_key == "m"
        and is_core_mail_enabled()
        and is_mail_commands_on_main_menu()
    ):
        handle_help_command(sender_id, interface)
        return
    if cfg_key is None or is_core_service_enabled(cfg_key):
        handler(sender_id, interface)
        return

    if module_entry:
        row, _instance = module_entry
        if manager.on_module_enter(row[0], sender_id, interface):
            return

    handle_help_command(sender_id, interface)


def handle_channel_directory_command(sender_id, interface, prefix_messages=None):
    response = _channel_directory_menu()
    messages = list(prefix_messages or []) + [response]
    send_user_messages(messages, sender_id, interface)
    update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 1})


def handle_channel_directory_steps(sender_id, message, step, state, interface, bbs_nodes):
    message = message.strip()
    if len(message) == 2 and message[1] == 'x':
        message = message[0]

    if step == 1:
        choice = message
        if choice.lower() == 'x':
            handle_help_command(sender_id, interface)
            return
        elif choice.lower() == 'v':
            _show_channel_pick_list(sender_id, interface)
        elif choice.lower() == 'p':
            send_message("Name channel for directory:", sender_id, interface)
            update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 3})

    elif step == 2:
        channel_index = _parse_int(message)
        channels = get_channels()
        menu_response = _channel_directory_menu()
        if channel_index is None or not (0 <= channel_index < len(channels)):
            send_message("Invalid channel number.", sender_id, interface)
            _show_channel_pick_list(sender_id, interface)
            return
        channel_name, channel_psk = channels[channel_index]
        send_user_messages([
            f"Channel Name: {channel_name}\nChannel PSK:\n{channel_psk}",
            menu_response,
        ], sender_id, interface)
        update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 1})

    elif step == 3:
        channel_name = message
        send_message("Send channel PSK:", sender_id, interface)
        update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 4, 'channel_name': channel_name})

    elif step == 4:
        channel_psk = message
        channel_name = state['channel_name']
        add_channel(
            channel_name,
            channel_psk,
            bbs_nodes,
            interface,
            defer_sync=True,
            publish='N',
        )
        send_user_messages([
            with_exit_prompt(
                f"Channel '{channel_name}' submitted. "
                "It will appear in the directory after the operator publishes it."
            ),
        ], sender_id, interface)
        update_user_state(sender_id, {'command': 'MAIN_MENU', 'step': 1})
