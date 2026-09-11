import argparse
import sqlite3

from rsmesh_bbs.venv_guard import require_venv

require_venv()

from rsmesh_bbs.version import APP_NAME, VERSION

from rsmesh_bbs.config_init import DEFAULT_CONFIG_FILE, export_sys_config_to_yaml, get_board_name, require_config_file
from rsmesh_bbs.utils import join_display_fields
from rsmesh_bbs.time_format import format_relative_time, format_timestamp
from rsmesh_bbs.db_operations import (
    initialize_database,
    get_db_connection,
    mark_bulletin_deleted,
    mark_channel_deleted,
    delete_mail_by_admin,
    sync_sysadmin_for_catalog_entry,
    add_sync_peer,
    update_sync_peer,
    delete_sync_peer,
    get_sync_peers,
    SYNC_PROTOCOLS,
    get_reconcile_bulletins,
    restore_reconcile_bulletin,
    confirm_reconcile_bulletin_delete,
    get_reconcile_channels,
    restore_reconcile_channel,
    confirm_reconcile_channel_delete,
    add_bulletin,
    add_mail,
    add_channel,
    get_unsynced_records,
    get_system_status,
    get_sync_status_label,
    reset_outbound_sync,
    normalize_sync_peer_last_heard,
    backfill_sync_peer_last_heard,
    ensure_sys_config_from_yaml,
    get_sys_config_entries,
    add_sys_config_entry,
    update_sys_config_entry,
    delete_sys_config_entry,
    get_sysadmin_nodes,
    add_sysadmin_node,
    update_sysadmin_node,
    delete_sysadmin_node,
    get_modules,
    update_module_flags,
    current_catalog_timestamp,
    export_node_catalog_to_csv,
    import_node_catalog_from_csv,
    export_channels_to_csv,
    import_channels_from_csv,
    get_all_mesh_nodes,
    get_mesh_node,
    add_mesh_node,
    update_mesh_node,
    delete_mesh_node,
    purge_mesh_nodes,
    export_mesh_nodes_to_csv,
    import_mesh_nodes_from_csv,
)
from rsmesh_bbs.module_loader import load_module_admin, module_admin_available
from rsmesh_bbs.backup import create_application_backup
from rsmesh_bbs.core_services import (
    CORE_SERVICE_KEYS,
    CORE_SERVICE_LABELS,
    ensure_core_services_config,
    is_core_bulletins_enabled,
    is_core_channels_enabled,
    is_core_mail_enabled,
    is_core_service_enabled,
    toggle_core_service,
)
from rsmesh_bbs import admin_ui

# Shared terminal layout and display helpers (core + module admin extensions)
console = admin_ui.console
DISPLAY_COLUMNS = admin_ui.DISPLAY_COLUMNS
DISPLAY_LINES = admin_ui.DISPLAY_LINES
SEPARATOR_COLUMNS = admin_ui.SEPARATOR_COLUMNS
HEADER_TITLE_LINE = admin_ui.HEADER_TITLE_LINE
HEADER_SEPARATOR_LINE = admin_ui.HEADER_SEPARATOR_LINE
HEADER_BLANK_LINE = admin_ui.HEADER_BLANK_LINE
CONTENT_START_LINE = admin_ui.CONTENT_START_LINE
CONTENT_END_LINE = admin_ui.CONTENT_END_LINE
MENU_SEPARATOR_LINE = admin_ui.MENU_SEPARATOR_LINE
MENU_INPUT_LINE = admin_ui.MENU_INPUT_LINE
PAGE_HEADER_LINE_COUNT = admin_ui.PAGE_HEADER_LINE_COUNT
MENU_OPTION_INDENT = admin_ui.MENU_OPTION_INDENT
CONTENT_LINES_PER_PAGE = admin_ui.CONTENT_LINES_PER_PAGE

clear_screen = admin_ui.clear_screen
print_bold = admin_ui.print_bold
print_separator = admin_ui.print_separator
input_bold = admin_ui.input_bold
print_page_header = admin_ui.print_page_header
begin_data_display = admin_ui.begin_data_display
paginate_display = admin_ui.paginate_display
_pad_to_line = admin_ui._pad_to_line
_print_no_data = admin_ui._print_no_data
_record_detail_lines = admin_ui.record_detail_lines
_display_record_detail = admin_ui.display_record_detail
_list_with_record_view = admin_ui.list_with_record_view

BULLETIN_BOARDS = ("General", "Info", "News", "Urgent")
BULLETIN_BOARD_DISPLAY_ORDER = ("Urgent", "General", "News", "Info")

def _paginate_select(page_title, lines, empty_message, select_prompt, cancelled_message):
    result = paginate_display(
        page_title, lines, empty_message=empty_message, select_prompt=select_prompt
    )
    if result is False:
        return False
    if result is None:
        return None
    _, choice = result
    if choice.upper() == 'X':
        _finish_cancelled(cancelled_message, page_title)
        return None
    return choice

def _paginate_select_exit(selection):
    """True when submenu handler should return early after paginate-select."""
    return selection is False or selection is None

def _prompt_at_bottom(lines_used, prompt):
    _pad_to_line(MENU_SEPARATOR_LINE, lines_used)
    print_separator()
    return input_bold(prompt)

def render_menu_screen(menu_name, body_lines):
    print_page_header(menu_name)
    content_line_count = 0
    for line in body_lines:
        if not line.strip():
            console.print()
            content_line_count += 1
            continue
        if line.startswith("0."):
            console.print()
            content_line_count += 1
        console.print(" " * MENU_OPTION_INDENT + line, style="bold", overflow="crop", no_wrap=True)
        content_line_count += 1
    return _prompt_at_bottom(PAGE_HEADER_LINE_COUNT + content_line_count, "Option: ")

def _print_line(message):
    print_bold(message[:DISPLAY_COLUMNS])

def _center_line(text):
    text = text[:DISPLAY_COLUMNS]
    padding = max(0, (DISPLAY_COLUMNS - len(text)) // 2)
    return (" " * padding + text)[:DISPLAY_COLUMNS]

def _format_rs_version_alert_summary(count):
    noun = "peer" if count == 1 else "peers"
    return f"Sync alerts: RS version: {count} {noun}"


def _build_system_status_content_lines(include_sync_peers=True):
    status = get_system_status()

    content_lines = [
        f"Total bulletins: {status['total_bulletins']}",
        f"Channels published: {status['channels_published']}",
        f"Channels unpublished: {status['channels_unpublished']}",
        f"Total mail messages: {status['total_mail']}",
        f"Unread mail messages: {status['unread_mail']}",
        join_display_fields(
            "Pending reconcile:",
            f"Bulletins: {status['reconcile_bulletins']}",
            f"Channels: {status['reconcile_channels']}",
        ),
        "",
    ]
    if include_sync_peers:
        if status['sync_peers']:
            peer_nodes = join_display_fields(*(row[1] for row in status['sync_peers']))
            content_lines.append(f"Sync peers: {peer_nodes}")
        else:
            content_lines.append("Sync peers: none")
    content_lines.append(_format_rs_version_alert_summary(status['rs_version_alert_count']))

    return content_lines

def _print_indented_status_lines(content_lines):
    indent = " " * MENU_OPTION_INDENT
    for line in content_lines:
        if line == "":
            console.print()
        else:
            print_bold((indent + line)[:DISPLAY_COLUMNS])

def show_splash_screen():
    clear_screen()
    print_page_header()
    console.print()
    print_bold(_center_line(f"****    {get_board_name()}    ****"))
    console.print()
    console.print()
    status_lines = _build_system_status_content_lines(include_sync_peers=False)
    _print_indented_status_lines(status_lines)

    lines_used = PAGE_HEADER_LINE_COUNT + 4 + len(status_lines)
    prompt_continue(lines_used)

def begin_form_screen(page_title):
    clear_screen()
    begin_data_display(page_title)

def _fetch_bulletins():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, board, sender_short_name, date, subject, deleted, unique_id, delete_reconcile, synced, pinned "
        "FROM bulletins"
    )
    return c.fetchall()

def _group_bulletins_by_board(bulletins):
    grouped = {board: [] for board in BULLETIN_BOARD_DISPLAY_ORDER}
    other = {}
    for bulletin in bulletins:
        board = bulletin[1]
        if board in grouped:
            grouped[board].append(bulletin)
        else:
            other.setdefault(board, []).append(bulletin)
    return grouped, other

def _bulletin_entry_lines(bulletin):
    bulletin_id, _board, poster, date, subject, deleted, unique_id, reconcile, _synced, pinned = bulletin
    sync_label = get_sync_status_label('bulletins', unique_id)
    return [
        "  " + join_display_fields(
            f"ID: {bulletin_id}",
            f"Poster: {poster}",
            f"Subject: {subject}",
            f"Date: {date}",
        ),
        "    " + join_display_fields(
            f"UID: {unique_id}",
            f"Del: {deleted}",
            f"Pinned: {pinned or 'N'}",
            f"Reconcile: {reconcile}",
            f"Sync: {sync_label}",
        ),
    ]

def _bulletin_lines(bulletins):
    if not bulletins:
        return []

    lines = []
    grouped, other = _group_bulletins_by_board(bulletins)
    for board in BULLETIN_BOARD_DISPLAY_ORDER:
        board_bulletins = grouped[board]
        if not board_bulletins:
            continue
        lines.append(f"{board}:")
        for bulletin in board_bulletins:
            lines.extend(_bulletin_entry_lines(bulletin))

    for board in sorted(other):
        board_bulletins = other[board]
        lines.append(f"{board}:")
        for bulletin in board_bulletins:
            lines.extend(_bulletin_entry_lines(bulletin))

    return lines

def list_bulletins():
    return _list_with_record_view(
        "List Bulletins",
        lambda: _bulletin_lines(_fetch_bulletins()),
        "No bulletins found.",
        _display_bulletin_detail,
    )

def _fetch_bulletin_entry(bulletin_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, board, sender_short_name, date, subject, content, deleted, unique_id, delete_reconcile, pinned "
        "FROM bulletins WHERE id = ?",
        (bulletin_id,),
    )
    return c.fetchone()

def _display_bulletin_detail(bulletin_id):
    row = _fetch_bulletin_entry(bulletin_id)
    if row is None:
        _display_record_detail(
            "View Bulletin",
            None,
            f"Bulletin {bulletin_id} not found.",
        )
        return
    bulletin_id, board, sender_short_name, date, subject, content, deleted, unique_id, delete_reconcile, pinned = row
    sync_label = get_sync_status_label('bulletins', unique_id)
    detail_lines = _record_detail_lines((
        ("ID", bulletin_id),
        ("Board", board),
        ("Poster", sender_short_name),
        ("Date", date),
        ("Subject", subject),
        ("Content", content),
        ("Unique ID", unique_id),
        ("Deleted", deleted),
        ("Pinned", pinned or 'N'),
        ("Delete Reconcile", delete_reconcile),
        ("Sync", sync_label),
    ))
    _display_record_detail("View Bulletin", detail_lines)

def _format_mail_party_label(short_name, hex_id):
    if short_name:
        return short_name
    if hex_id:
        return hex_id
    return "Unknown"

def _fetch_mail():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, sender, sender_short_name, recipient, recipient_short_name, date, subject, unique_id, synced "
        "FROM mail"
    )
    return c.fetchall()

def _mail_entry_lines(mail_row):
    mail_id, sender, sender_short_name, recipient, recipient_short_name, _date, subject, unique_id, _synced = mail_row
    sync_label = get_sync_status_label('mail', unique_id)
    return [
        join_display_fields(
            f"ID: {mail_id}",
            f"To: {_format_mail_party_label(recipient_short_name, recipient)}",
            f"From: {_format_mail_party_label(sender_short_name, sender)}",
            f"Sync: {sync_label}",
        ),
        f"  Subject: {subject}",
    ]

def _mail_lines(mail_rows):
    if not mail_rows:
        return []
    lines = []
    for mail_row in mail_rows:
        lines.extend(_mail_entry_lines(mail_row))
    return lines

def list_mail():
    return _list_with_record_view(
        "List Mail",
        lambda: _mail_lines(_fetch_mail()),
        "No mail found.",
        _display_mail_detail,
    )

def _fetch_mail_entry(mail_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, sender, sender_short_name, recipient, recipient_short_name, date, subject, content, unique_id, read "
        "FROM mail WHERE id = ?",
        (mail_id,),
    )
    return c.fetchone()

def _display_mail_detail(mail_id):
    row = _fetch_mail_entry(mail_id)
    if row is None:
        _display_record_detail(
            "View Mail",
            None,
            f"Mail {mail_id} not found.",
        )
        return
    mail_id, sender, sender_short_name, recipient, recipient_short_name, date, subject, content, unique_id, read_flag = row
    sync_label = get_sync_status_label('mail', unique_id)
    detail_lines = _record_detail_lines((
        ("ID", mail_id),
        ("Sender Hex", sender or ""),
        ("Sender Short Name", sender_short_name or ""),
        ("Recipient Hex", recipient or ""),
        ("Recipient Short Name", recipient_short_name or ""),
        ("Date", date),
        ("Subject", subject),
        ("Content", content),
        ("Unique ID", unique_id),
        ("Read", read_flag or "N"),
        ("Sync", sync_label),
    ))
    _display_record_detail("View Mail", detail_lines)

def _fetch_channels():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, name, psk, synced, publish, unique_id, deleted, delete_reconcile "
        "FROM channels"
    )
    return c.fetchall()

def _channel_entry_lines(channel):
    channel_id, name, psk, _synced, publish, unique_id, deleted, reconcile = channel
    sync_label = '*' if publish == 'N' else get_sync_status_label('channels', unique_id)
    return [
        join_display_fields(
            f"ID: {channel_id}",
            f"Name: {name}",
            f"Sync: {sync_label}",
            f"Publish: {publish}",
        ),
        "    " + join_display_fields(
            f"PSK: {psk}",
            f"Del: {deleted}",
            f"Reconcile: {reconcile}",
        ),
    ]

def _channel_lines(channels):
    if not channels:
        return []
    lines = []
    for channel in channels:
        lines.extend(_channel_entry_lines(channel))
    return lines

def list_channels():
    return _list_with_record_view(
        "List Channels",
        lambda: _channel_lines(_fetch_channels()),
        "No channels found.",
        _display_channel_detail,
    )

def _fetch_channel_entry(channel_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, name, psk, synced, publish, unique_id, deleted, delete_reconcile FROM channels WHERE id = ?",
        (channel_id,),
    )
    return c.fetchone()

def _display_channel_detail(channel_id):
    row = _fetch_channel_entry(channel_id)
    if row is None:
        _display_record_detail(
            "View Channel",
            None,
            f"Channel {channel_id} not found.",
        )
        return
    channel_id, name, psk, _synced, publish, unique_id, deleted, delete_reconcile = row
    sync_label = '*' if publish == 'N' else get_sync_status_label('channels', unique_id)
    detail_lines = _record_detail_lines((
        ("ID", channel_id),
        ("Name", name),
        ("PSK", psk),
        ("Publish", publish),
        ("Unique ID", unique_id),
        ("Deleted", deleted),
        ("Delete Reconcile", delete_reconcile),
        ("Sync", sync_label),
    ))
    _display_record_detail("View Channel", detail_lines)

def _read_multiline_content():
    print_bold("Enter content (type END on its own line when finished):")
    lines = []
    while True:
        line = input_bold("")
        if line.strip().upper() == 'END':
            break
        lines.append(line)
    return '\n'.join(lines).rstrip('\n')

def add_bulletin_entry():
    begin_form_screen("Add Bulletin")
    print_bold(f"Boards: {', '.join(BULLETIN_BOARDS)}")
    board = input_bold("Board: ").strip()
    if board not in BULLETIN_BOARDS:
        _finish_action_message(f"Invalid board. Choose one of: {', '.join(BULLETIN_BOARDS)}", "Add Bulletin")
        return
    sender_short_name = input_bold("Poster short name: ").strip()
    subject = input_bold("Subject: ").strip()
    if not sender_short_name or not subject:
        _finish_action_message("Poster short name and subject are required.", "Add Bulletin")
        return
    content = _read_multiline_content()
    unique_id = add_bulletin(board, sender_short_name, subject, content, None, None)
    if board == "Urgent":
        from rsmesh_bbs.urgent_alerts import enqueue_pending_urgent_alert, urgent_alert_local_enabled

        if urgent_alert_local_enabled():
            enqueue_pending_urgent_alert(unique_id, sender_short_name, subject)
    _finish_action_message(f"Bulletin added (unique ID: {unique_id}).", "Add Bulletin")

def edit_bulletin_entry():
    bulletin_id = _paginate_select(
        "Edit Bulletin",
        _bulletin_lines(_fetch_bulletins()),
        "No bulletins found.",
        "Enter ID or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(bulletin_id):
        return bulletin_id

    begin_form_screen("Edit Bulletin")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT board, sender_short_name, subject, content, unique_id, pinned FROM bulletins WHERE id = ?",
        (bulletin_id,)
    )
    current = c.fetchone()
    if current is None:
        _finish_action_message("Bulletin not found.", "Edit Bulletin")
        return

    board, sender_short_name, subject, content, unique_id, pinned = current
    print_bold("Press Enter to keep the current value.")
    print_bold(f"Boards: {', '.join(BULLETIN_BOARDS)}")
    new_board = input_bold(f"Board [{board}]: ").strip() or board
    if new_board not in BULLETIN_BOARDS:
        _finish_action_message(f"Invalid board. Choose one of: {', '.join(BULLETIN_BOARDS)}", "Edit Bulletin")
        return
    sender_short_name = input_bold(f"Poster short name [{sender_short_name}]: ").strip() or sender_short_name
    subject = input_bold(f"Subject [{subject}]: ").strip() or subject
    if input_bold("Edit content? (Y/N) [N]: ").strip().upper() == 'Y':
        print_bold(f"Current content:\n{content}")
        content = _read_multiline_content()
    pinned = _normalize_yn(input_bold(f"Pinned (Y/N) [{pinned or 'N'}]: "), pinned or 'N')

    c.execute(
        "UPDATE bulletins SET board = ?, sender_short_name = ?, subject = ?, content = ?, pinned = ?, synced = 'N' WHERE id = ?",
        (new_board, sender_short_name, subject, content, pinned, bulletin_id)
    )
    conn.commit()
    reset_outbound_sync('bulletins', unique_id, 'id', bulletin_id)
    _finish_action_message(f"Bulletin {bulletin_id} updated.", "Edit Bulletin")

def send_mail_entry():
    begin_form_screen("Send Mail")
    sender_id = input_bold("Sender node ID (e.g. !9e9d8704): ").strip()
    sender_short_name = input_bold("Sender short name: ").strip()
    recipient_id = input_bold("Recipient node ID or short name: ").strip()
    subject = input_bold("Subject: ").strip()
    if not sender_id or not sender_short_name or not recipient_id or not subject:
        _finish_action_message(
            "Sender node ID, sender short name, recipient, and subject are required.",
            "Send Mail",
        )
        return
    content = _read_multiline_content()
    unique_id, final_recipient = add_mail(
        sender_id, sender_short_name, recipient_id, subject, content, None, None
    )
    _finish_action_message(
        f"Mail sent to {final_recipient} ({unique_id})",
        "Send Mail",
    )

def edit_mail_entry():
    mail_id = _paginate_select(
        "Edit Mail",
        _mail_lines(_fetch_mail()),
        "No mail found.",
        "Enter ID or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(mail_id):
        return mail_id

    begin_form_screen("Edit Mail")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT sender, sender_short_name, recipient, subject, content, unique_id FROM mail WHERE id = ?",
        (mail_id,)
    )
    current = c.fetchone()
    if current is None:
        _finish_action_message("Mail not found.", "Edit Mail")
        return

    sender, sender_short_name, recipient, subject, content, unique_id = current
    print_bold("Press Enter to keep the current value.")
    sender = input_bold(f"Sender node ID [{sender}]: ").strip() or sender
    sender_short_name = input_bold(f"Sender short name [{sender_short_name}]: ").strip() or sender_short_name
    recipient = input_bold(f"Recipient [{recipient}]: ").strip() or recipient
    subject = input_bold(f"Subject [{subject}]: ").strip() or subject
    if input_bold("Edit content? (Y/N) [N]: ").strip().upper() == 'Y':
        print_bold(f"Current content:\n{content}")
        content = _read_multiline_content()

    c.execute(
        "UPDATE mail SET sender = ?, sender_short_name = ?, recipient = ?, subject = ?, content = ?, synced = 'N' "
        "WHERE id = ?",
        (sender, sender_short_name, recipient, subject, content, mail_id)
    )
    conn.commit()
    reset_outbound_sync('mail', unique_id, 'id', mail_id)
    _finish_action_message(f"Mail {mail_id} updated.", "Edit Mail")

def add_channel_entry():
    begin_form_screen("Add Channel")
    name = input_bold("Channel name: ").strip()
    psk = input_bold("Channel PSK: ").strip()
    if not name or not psk:
        _finish_action_message("Channel name and PSK are required.", "Add Channel")
        return
    add_channel(name, psk)
    _finish_action_message(f"Channel '{name}' added.", "Add Channel")

def edit_channel_entry():
    channel_id = _paginate_select(
        "Edit Channel",
        _channel_lines(_fetch_channels()),
        "No channels found.",
        "Enter ID or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(channel_id):
        return channel_id

    begin_form_screen("Edit Channel")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, psk, publish, unique_id FROM channels WHERE id = ?", (channel_id,))
    current = c.fetchone()
    if current is None:
        _finish_action_message("Channel not found.", "Edit Channel")
        return

    name, psk, publish, unique_id = current
    print_bold("Press Enter to keep the current value.")
    name = input_bold(f"Channel name [{name}]: ").strip() or name
    psk = input_bold(f"Channel PSK [{psk}]: ").strip() or psk
    publish = _normalize_yn(input_bold(f"Publish (Y/N) [{publish}]: "), publish)

    if publish == 'Y':
        c.execute(
            "UPDATE channels SET name = ?, psk = ?, publish = ?, synced = 'N' WHERE id = ?",
            (name, psk, publish, channel_id)
        )
        conn.commit()
        reset_outbound_sync('channels', unique_id, 'id', channel_id)
    else:
        c.execute(
            "UPDATE channels SET name = ?, psk = ?, publish = ?, synced = 'Y' WHERE id = ?",
            (name, psk, publish, channel_id)
        )
        conn.commit()
    _finish_action_message(f"Channel {channel_id} updated.", "Edit Channel")

def delete_bulletin():
    choice = _paginate_select(
        "Delete Bulletins",
        _bulletin_lines(_fetch_bulletins()),
        "No bulletins found.",
        "Enter ID(s) or X=cancel:",
        "Deletion cancelled.",
    )
    if _paginate_select_exit(choice):
        return choice

    bulletin_ids = [item.strip() for item in choice.split(',') if item.strip()]
    if 'X' in [item.upper() for item in bulletin_ids]:
        _finish_cancelled("Deletion cancelled.", "Delete Bulletins")
        return

    marked = []
    for bulletin_id in bulletin_ids:
        if mark_bulletin_deleted(bulletin_id.strip()):
            marked.append(bulletin_id.strip())
    message = (
        f"Bulletin(s) with ID(s) {', '.join(marked)} marked for deletion. "
        "The BBS server will purge and sync when running."
    )
    if len(marked) != len([item.strip() for item in bulletin_ids if item.strip()]):
        message += "\nOne or more bulletin IDs were not found or were already marked deleted."
    _finish_action_message(message, "Delete Bulletins")

def delete_mail():
    choice = _paginate_select(
        "Delete Mail",
        _mail_lines(_fetch_mail()),
        "No mail found.",
        "Enter ID(s) or X=cancel:",
        "Deletion cancelled.",
    )
    if _paginate_select_exit(choice):
        return choice

    mail_ids = [item.strip() for item in choice.split(',') if item.strip()]
    if 'X' in [item.upper() for item in mail_ids]:
        _finish_cancelled("Deletion cancelled.", "Delete Mail")
        return

    deleted = []
    for mail_id in mail_ids:
        if delete_mail_by_admin(mail_id.strip()):
            deleted.append(mail_id.strip())
    message = (
        f"Mail with ID(s) {', '.join(deleted)} deleted."
        if deleted else "No mail deleted."
    )
    if deleted:
        message += "\nThe BBS server will sync deletes to peers when running."
    if len(deleted) != len([item.strip() for item in mail_ids if item.strip()]):
        message += "\nOne or more mail IDs were not found."
    _finish_action_message(message, "Delete Mail")

def delete_channel():
    choice = _paginate_select(
        "Delete Channels",
        _channel_lines(_fetch_channels()),
        "No channels found.",
        "Enter ID(s) or X=cancel:",
        "Deletion cancelled.",
    )
    if _paginate_select_exit(choice):
        return choice

    channel_ids = [item.strip() for item in choice.split(',') if item.strip()]
    if 'X' in [item.upper() for item in channel_ids]:
        _finish_cancelled("Deletion cancelled.", "Delete Channels")
        return

    marked = []
    for channel_id in channel_ids:
        if mark_channel_deleted(channel_id.strip()):
            marked.append(channel_id.strip())
    message = (
        f"Channel(s) with ID(s) {', '.join(marked)} marked for deletion. "
        "The BBS server will purge and sync when running."
    )
    if len(marked) != len([item.strip() for item in channel_ids if item.strip()]):
        message += "\nOne or more channel IDs were not found or were already marked deleted."
    _finish_action_message(message, "Delete Channels")

def _normalize_yn(value, default='N'):
    value = (value or default).strip().upper()
    return value if value in ('Y', 'N') else default

def _fetch_node_catalog():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, long_name, short_name, node_hex_username, mesh_admin, bbs_admin "
        "FROM node_catalog ORDER BY short_name COLLATE NOCASE, id"
    )
    return c.fetchall()

def _fetch_node_catalog_entry(row_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """SELECT id, long_name, short_name, node_hex_username, mesh_admin, bbs_admin,
                  bbs_mail_forward_to, has_gps, public_key, private_key, ble_pin, hardware, comment,
                  created, updated
           FROM node_catalog WHERE id = ?""",
        (row_id,),
    )
    return c.fetchone()

def _node_catalog_detail_lines(row):
    row_id, long_name, short_name, node_hex_username, mesh_admin, bbs_admin, bbs_mail_forward_to, has_gps, public_key, private_key, ble_pin, hardware, comment, created, updated = row
    return _record_detail_lines((
        ("ID", row_id),
        ("Short Name", short_name),
        ("Long Name", long_name),
        ("Node Hex Username", node_hex_username),
        ("Mesh Admin", mesh_admin),
        ("BBS Admin", bbs_admin),
        ("BBS Mail Forward To", bbs_mail_forward_to or ""),
        ("Has GPS", has_gps),
        ("Public Key", public_key),
        ("Private Key", private_key or ""),
        ("BLE PIN", ble_pin),
        ("Hardware", hardware or ""),
        ("Comment", comment or ""),
        ("Created", created or ""),
        ("Updated", updated or ""),
    ))

def _display_node_catalog_detail(row_id):
    row = _fetch_node_catalog_entry(row_id)
    if row is None:
        _display_record_detail(
            "View Node Catalog Entry",
            None,
            f"Node catalog entry {row_id} not found.",
        )
        return
    _display_record_detail("View Node Catalog Entry", _node_catalog_detail_lines(row))

def _node_catalog_lines(rows):
    if not rows:
        return []
    lines = []
    for row in rows:
        row_id, long_name, short_name, node_hex, mesh_admin, bbs_admin = row
        admin = 'Y' if mesh_admin == 'Y' or bbs_admin == 'Y' else 'N'
        lines.append(
            join_display_fields(
                f"ID: {row_id}",
                f"Short: {short_name}",
                f"Long: {long_name}",
                f"Node: {node_hex}",
                f"Admin: {admin}",
            )
        )
    return lines

def list_node_catalog():
    return _list_with_record_view(
        "List Node Catalog",
        lambda: _node_catalog_lines(_fetch_node_catalog()),
        "No node catalog entries found.",
        _display_node_catalog_detail,
    )

def add_node_catalog_entry():
    begin_form_screen("Add Node Catalog Entry")
    long_name = input_bold("Long name: ").strip()
    short_name = input_bold("Short name: ").strip()
    node_hex_username = input_bold("Node hex username (e.g. !9e9d8704): ").strip()
    mesh_admin = _normalize_yn(input_bold("Mesh admin (Y/N) [N]: "))
    bbs_admin = _normalize_yn(input_bold("BBS admin (Y/N) [N]: "))
    bbs_mail_forward_to = input_bold("BBS mail forward to (optional): ").strip() or None
    has_gps = _normalize_yn(input_bold("Has GPS (Y/N) [N]: "))
    public_key = input_bold("Public key (optional): ").strip() or None
    private_key = input_bold("Private key (optional): ").strip() or None
    ble_pin = input_bold("BLE PIN [123456]: ").strip() or '123456'
    hardware = input_bold("Hardware (optional): ").strip() or None
    comment = input_bold("Comment (optional): ").strip() or None

    if not long_name or not short_name or not node_hex_username:
        _finish_action_message(
            "Long name, short name, and node hex username are required.",
            "Add Node Catalog Entry",
        )
        return

    conn = get_db_connection()
    c = conn.cursor()
    now = current_catalog_timestamp()
    c.execute(
        """INSERT INTO node_catalog (
               long_name, short_name, node_hex_username, mesh_admin, bbs_admin,
               bbs_mail_forward_to, has_gps, public_key, private_key, ble_pin, hardware, comment,
               created, updated
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (long_name, short_name, node_hex_username, mesh_admin, bbs_admin,
         bbs_mail_forward_to, has_gps, public_key, private_key, ble_pin, hardware, comment,
         now, now)
    )
    conn.commit()
    sync_sysadmin_for_catalog_entry(short_name, node_hex_username, bbs_admin)
    _finish_action_message(f"Node catalog entry added for {short_name}.", "Add Node Catalog Entry")

def edit_node_catalog_entry():
    row_id = _paginate_select(
        "Edit Node Catalog Entry",
        _node_catalog_lines(_fetch_node_catalog()),
        "No node catalog entries found.",
        "Enter catalog ID or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(row_id):
        return row_id

    begin_form_screen("Edit Node Catalog Entry")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """SELECT long_name, short_name, node_hex_username, mesh_admin, bbs_admin,
                  bbs_mail_forward_to, has_gps, public_key, private_key, ble_pin, hardware, comment
           FROM node_catalog WHERE id = ?""",
        (row_id,)
    )
    current = c.fetchone()
    if current is None:
        _finish_action_message("Node catalog entry not found.", "Edit Node Catalog Entry")
        return

    long_name, short_name, node_hex_username, mesh_admin, bbs_admin, bbs_mail_forward_to, has_gps, public_key, private_key, ble_pin, hardware, comment = current
    old_node_hex_username = node_hex_username

    print_bold("Press Enter to keep the current value.")
    long_name = input_bold(f"Long name [{long_name}]: ").strip() or long_name
    short_name = input_bold(f"Short name [{short_name}]: ").strip() or short_name
    node_hex_username = input_bold(f"Node hex username [{node_hex_username}]: ").strip() or node_hex_username
    mesh_admin = _normalize_yn(input_bold(f"Mesh admin (Y/N) [{mesh_admin}]: "), mesh_admin)
    bbs_admin = _normalize_yn(input_bold(f"BBS admin (Y/N) [{bbs_admin}]: "), bbs_admin)
    fwd = input_bold(f"BBS mail forward to [{bbs_mail_forward_to or ''}]: ").strip()
    if fwd:
        bbs_mail_forward_to = fwd
    has_gps = _normalize_yn(input_bold(f"Has GPS (Y/N) [{has_gps}]: "), has_gps)
    pk = input_bold(f"Public key [{public_key or ''}]: ").strip()
    if pk:
        public_key = pk
    pk = input_bold(f"Private key [{private_key or ''}]: ").strip()
    if pk:
        private_key = pk
    ble_pin = input_bold(f"BLE PIN [{ble_pin}]: ").strip() or ble_pin
    hw = input_bold(f"Hardware [{hardware or ''}]: ").strip()
    if hw:
        hardware = hw
    cm = input_bold(f"Comment [{comment or ''}]: ").strip()
    if cm:
        comment = cm

    c.execute(
        """UPDATE node_catalog
           SET long_name = ?, short_name = ?, node_hex_username = ?, mesh_admin = ?, bbs_admin = ?,
               bbs_mail_forward_to = ?, has_gps = ?, public_key = ?, private_key = ?, ble_pin = ?,
               hardware = ?, comment = ?, updated = ?
           WHERE id = ?""",
        (long_name, short_name, node_hex_username, mesh_admin, bbs_admin,
         bbs_mail_forward_to, has_gps, public_key, private_key, ble_pin, hardware, comment,
         current_catalog_timestamp(), row_id)
    )
    conn.commit()

    if old_node_hex_username != node_hex_username:
        sync_sysadmin_for_catalog_entry(short_name, old_node_hex_username, 'N')
    sync_sysadmin_for_catalog_entry(short_name, node_hex_username, bbs_admin)
    _finish_action_message(f"Node catalog entry {row_id} updated.", "Edit Node Catalog Entry")

def delete_node_catalog_entry():
    choice = _paginate_select(
        "Delete Node Catalog Entry",
        _node_catalog_lines(_fetch_node_catalog()),
        "No node catalog entries found.",
        "Enter catalog ID(s) or X=cancel:",
        "Deletion cancelled.",
    )
    if _paginate_select_exit(choice):
        return choice

    row_ids = [item.strip() for item in choice.split(',') if item.strip()]
    if 'X' in [item.upper() for item in row_ids]:
        _finish_cancelled("Deletion cancelled.", "Delete Node Catalog Entry")
        return

    conn = get_db_connection()
    c = conn.cursor()
    deleted = []
    not_found = []
    for row_id in row_ids:
        c.execute("SELECT node_hex_username FROM node_catalog WHERE id = ?", (row_id.strip(),))
        result = c.fetchone()
        if result is None:
            not_found.append(row_id.strip())
            continue
        node_hex_username = result[0]
        c.execute("DELETE FROM sysadmin_nodes WHERE node_hex_username = ?", (node_hex_username,))
        c.execute("DELETE FROM node_catalog WHERE id = ?", (row_id.strip(),))
        deleted.append(row_id.strip())
    conn.commit()
    if deleted:
        message = f"Node catalog entry(s) {', '.join(deleted)} deleted."
        if not_found:
            message += f"\nNot found: {', '.join(not_found)}."
    elif not_found:
        message = f"Node catalog entry(s) not found: {', '.join(not_found)}."
    else:
        message = "No node catalog entries were deleted."
    _finish_action_message(message, "Delete Node Catalog Entry")

def _prompt_csv_filename(default):
    return input_bold(
        f"Enter filename (full path allowed) [{default}]: "
    ).strip() or default

def _prompt_node_catalog_csv_filename(default="node_catalog.csv"):
    return _prompt_csv_filename(default)

def export_node_catalog_csv_entry():
    page_title = "Export to CSV"
    begin_form_screen(page_title)
    file_path = _prompt_node_catalog_csv_filename()
    try:
        count = export_node_catalog_to_csv(file_path)
        _finish_action_message(
            f"Exported {count} node catalog entr{'y' if count == 1 else 'ies'} to {file_path}.",
            page_title,
        )
    except OSError as exc:
        _finish_action_message(f"Export failed: {exc}", page_title)

def import_node_catalog_csv_entry():
    page_title = "Import from CSV"
    begin_form_screen(page_title)
    file_path = _prompt_node_catalog_csv_filename()
    mode = input_bold(
        "[R]eplace existing data or [A]ppend to existing data? [A]: "
    ).strip().upper()
    if mode not in ('R', 'A', ''):
        _finish_action_message("Import cancelled.", page_title)
        return
    replace = mode == 'R'
    try:
        result = import_node_catalog_from_csv(file_path, replace=replace)
    except (OSError, ValueError) as exc:
        _finish_action_message(f"Import failed: {exc}", page_title)
        return

    message_lines = [
        f"Imported from {file_path} ({'replace' if replace else 'append'}).",
        f"Inserted: {result['inserted']}",
        f"Updated: {result['updated']}",
        f"Unchanged: {result['unchanged']}",
    ]
    if result['errors']:
        message_lines.append(f"Skipped rows: {len(result['errors'])}")
        message_lines.extend(result['errors'][:5])
        if len(result['errors']) > 5:
            message_lines.append(f"... and {len(result['errors']) - 5} more.")
    _finish_action_message("\n".join(message_lines), page_title)

def export_channels_csv_entry():
    page_title = "Export to CSV"
    begin_form_screen(page_title)
    file_path = _prompt_csv_filename("channels.csv")
    try:
        count = export_channels_to_csv(file_path)
        _finish_action_message(
            f"Exported {count} channel{'s' if count != 1 else ''} to {file_path}.",
            page_title,
        )
    except OSError as exc:
        _finish_action_message(f"Export failed: {exc}", page_title)

def import_channels_csv_entry():
    page_title = "Import from CSV"
    begin_form_screen(page_title)
    file_path = _prompt_csv_filename("channels.csv")
    mode = input_bold(
        "[R]eplace existing data or [A]ppend to existing data? [A]: "
    ).strip().upper()
    if mode not in ('R', 'A', ''):
        _finish_action_message("Import cancelled.", page_title)
        return
    replace = mode == 'R'
    try:
        result = import_channels_from_csv(file_path, replace=replace)
    except (OSError, ValueError) as exc:
        _finish_action_message(f"Import failed: {exc}", page_title)
        return

    message_lines = [
        f"Imported from {file_path} ({'replace' if replace else 'append'}).",
        f"Inserted: {result['inserted']}",
        f"Updated: {result['updated']}",
        f"Unchanged: {result['unchanged']}",
    ]
    if result['errors']:
        message_lines.append(f"Skipped rows: {len(result['errors'])}")
        message_lines.extend(result['errors'][:5])
        if len(result['errors']) > 5:
            message_lines.append(f"... and {len(result['errors']) - 5} more.")
    _finish_action_message("\n".join(message_lines), page_title)

def _mesh_node_lines(rows):
    if not rows:
        return []
    lines = []
    for node_id, short_name, long_name, last_heard, last_updated in rows:
        lines.append(
            join_display_fields(
                f"Node: {node_id}",
                f"Short: {short_name or '-'}",
                f"Long: {long_name or '-'}",
                f"Seen: {format_relative_time(last_heard)}",
            )
        )
    return lines

def _mesh_node_detail_lines(row):
    node_id, short_name, long_name, last_heard, last_updated = row
    return _record_detail_lines((
        ("Node ID", node_id),
        ("Short Name", short_name or ""),
        ("Long Name", long_name or ""),
        ("Last Heard", format_timestamp(last_heard) if last_heard else ""),
        ("Last Heard (relative)", format_relative_time(last_heard) if last_heard else ""),
        ("Last Updated", format_timestamp(last_updated) if last_updated else ""),
    ))

def _display_mesh_node_detail(node_id):
    row = get_mesh_node(node_id)
    if row is None:
        _display_record_detail(
            "View Mesh Node",
            None,
            f"Mesh node {node_id} not found.",
        )
        return
    _display_record_detail("View Mesh Node", _mesh_node_detail_lines(row))

def list_mesh_nodes():
    return _list_with_record_view(
        "List Mesh Nodes",
        lambda: _mesh_node_lines(get_all_mesh_nodes()),
        "No mesh nodes found.",
        _display_mesh_node_detail,
    )

def add_mesh_node_entry():
    begin_form_screen("Add Mesh Node")
    node_id = input_bold("Node hex ID (e.g. !9e9d8704): ").strip()
    short_name = input_bold("Short name (optional): ").strip() or None
    long_name = input_bold("Long name (optional): ").strip() or None
    last_heard = input_bold("Last heard unix timestamp (optional): ").strip() or None
    if not node_id:
        _finish_action_message("Node hex ID is required.", "Add Mesh Node")
        return
    if get_mesh_node(node_id):
        _finish_action_message(f"Mesh node {node_id} already exists.", "Add Mesh Node")
        return
    if add_mesh_node(node_id, short_name, long_name, last_heard):
        _finish_action_message(f"Mesh node {node_id} added.", "Add Mesh Node")
    else:
        _finish_action_message("Could not add mesh node.", "Add Mesh Node")

def edit_mesh_node_entry():
    rows = get_all_mesh_nodes()
    node_id = _paginate_select(
        "Edit Mesh Node",
        _mesh_node_lines(rows),
        "No mesh nodes found.",
        "Enter node ID or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(node_id):
        return node_id

    current = get_mesh_node(node_id)
    if current is None:
        _finish_action_message("Mesh node not found.", "Edit Mesh Node")
        return

    _, short_name, long_name, last_heard, _last_updated = current
    begin_form_screen("Edit Mesh Node")
    print_bold("Press Enter to keep the current value.")
    short_name = input_bold(f"Short name [{short_name or ''}]: ").strip() or short_name
    long_name = input_bold(f"Long name [{long_name or ''}]: ").strip() or long_name
    last_heard_input = input_bold(
        f"Last heard unix timestamp [{last_heard or ''}]: "
    ).strip()
    if last_heard_input:
        last_heard = last_heard_input
    if update_mesh_node(node_id, short_name, long_name, last_heard):
        _finish_action_message(f"Mesh node {node_id} updated.", "Edit Mesh Node")
    else:
        _finish_action_message("Could not update mesh node.", "Edit Mesh Node")

def delete_mesh_node_entry():
    rows = get_all_mesh_nodes()
    node_id = _paginate_select(
        "Delete Mesh Node",
        _mesh_node_lines(rows),
        "No mesh nodes found.",
        "Enter node ID or X=cancel:",
        "Deletion cancelled.",
    )
    if _paginate_select_exit(node_id):
        return node_id

    if delete_mesh_node(node_id):
        _finish_action_message(f"Mesh node {node_id} deleted.", "Delete Mesh Node")
    else:
        _finish_action_message("Mesh node not found.", "Delete Mesh Node")

def _prompt_mesh_nodes_csv_filename(default="mesh_nodes.csv"):
    return _prompt_csv_filename(default)

def export_mesh_nodes_csv_entry():
    page_title = "Export to CSV"
    begin_form_screen(page_title)
    file_path = _prompt_mesh_nodes_csv_filename()
    try:
        count = export_mesh_nodes_to_csv(file_path)
        _finish_action_message(
            f"Exported {count} mesh node{'s' if count != 1 else ''} to {file_path}.",
            page_title,
        )
    except OSError as exc:
        _finish_action_message(f"Export failed: {exc}", page_title)

def import_mesh_nodes_csv_entry():
    page_title = "Import from CSV"
    begin_form_screen(page_title)
    file_path = _prompt_mesh_nodes_csv_filename()
    mode = input_bold(
        "[R]eplace existing data or [A]ppend to existing data? [A]: "
    ).strip().upper()
    if mode not in ('R', 'A', ''):
        _finish_action_message("Import cancelled.", page_title)
        return
    replace = mode == 'R'
    try:
        result = import_mesh_nodes_from_csv(file_path, replace=replace)
    except (OSError, ValueError) as exc:
        _finish_action_message(f"Import failed: {exc}", page_title)
        return

    message_lines = [
        f"Imported from {file_path} ({'replace' if replace else 'append'}).",
        f"Inserted: {result['inserted']}",
        f"Updated: {result['updated']}",
        f"Unchanged: {result['unchanged']}",
    ]
    if result['errors']:
        message_lines.append(f"Skipped rows: {len(result['errors'])}")
        message_lines.extend(result['errors'][:5])
        if len(result['errors']) > 5:
            message_lines.append(f"... and {len(result['errors']) - 5} more.")
    _finish_action_message("\n".join(message_lines), page_title)

def purge_mesh_nodes_entry():
    begin_form_screen("Purge Mesh Nodes")
    confirm = input_bold("Delete ALL mesh nodes? This cannot be undone. (Y/N) [N]: ").strip().upper()
    if confirm != 'Y':
        _finish_action_message("Purge cancelled.", "Purge Mesh Nodes")
        return
    purge_mesh_nodes()
    _finish_action_message("All mesh nodes deleted.", "Purge Mesh Nodes")

def _sync_peer_alert_field(peer):
    if len(peer) <= 11 or (peer[11] or 'N') != 'Y':
        return None
    seen = peer[12] if len(peer) > 12 and peer[12] is not None else '?'
    return f"Alert: received RS v{seen}"


def _sync_peer_flag_lines(peer, last_heard_label=None):
    if len(peer) < 8:
        sync_bulletins, sync_mail, sync_channels = 'Y', 'Y', 'Y'
        sync_mesh_nodes = 'N'
        ingest_bulletins, ingest_channels = 'Y', 'Y'
    else:
        sync_bulletins, sync_mail, sync_channels = peer[5], peer[6], peer[7]
        sync_mesh_nodes = peer[8] if len(peer) > 8 else 'N'
        ingest_bulletins = peer[9] if len(peer) > 9 else 'Y'
        ingest_channels = peer[10] if len(peer) > 10 else 'Y'
    mail_line_fields = [
        f"Mail: {sync_mail or 'Y'}",
        f"Mesh nodes: {sync_mesh_nodes or 'N'}",
    ]
    if last_heard_label:
        mail_line_fields.append(f"Last heard: {last_heard_label}")
    return [
        "  " + join_display_fields(
            f"In: bulletins {ingest_bulletins or 'Y'}",
            f"channels {ingest_channels or 'Y'}",
            f"Out: bulletins {sync_bulletins or 'Y'}",
            f"channels {sync_channels or 'Y'}",
        ),
        "  " + join_display_fields(*mail_line_fields),
    ]


def _sync_peer_lines(rows):
    if not rows:
        return []
    lines = []
    for peer in rows:
        peer_id, bbs_node, bbs_name, sync_protocol, last_heard = peer[:5]
        heard = format_relative_time(normalize_sync_peer_last_heard(last_heard))
        fields = [
            f"ID: {peer_id}",
            f"Node: {bbs_node}",
        ]
        if bbs_name:
            fields.append(f"Name: {bbs_name}")
        enabled = peer[13] if len(peer) > 13 else 'Y'
        fields.extend([
            f"Protocol: {sync_protocol}",
            f"Enabled: {enabled or 'Y'}",
        ])
        alert = _sync_peer_alert_field(peer)
        if alert:
            fields.append(alert)
        lines.append(join_display_fields(*fields))
        lines.extend(_sync_peer_flag_lines(peer, heard))
    return lines

def list_sync_peers():
    paginate_display("List Sync Peers", _sync_peer_lines(get_sync_peers()), empty_message="No sync peers found.")
    return False

def add_sync_peer_entry():
    begin_form_screen("Add Sync Peer")
    bbs_node = input_bold("BBS node (e.g. !17d7e4b7): ").strip()
    bbs_name = input_bold("BBS name (optional): ").strip() or None
    sync_protocol = input_bold(f"Sync protocol ({'/'.join(SYNC_PROTOCOLS)}) [tc2]: ").strip() or 'tc2'
    sync_bulletins = _normalize_yn(input_bold("Sync bulletins out (Y/N) [Y]: "), 'Y')
    sync_mail = _normalize_yn(input_bold("Sync mail in/out (Y/N) [Y]: "), 'Y')
    sync_channels = _normalize_yn(input_bold("Sync channels out (Y/N) [Y]: "), 'Y')
    sync_mesh_nodes = None
    if sync_protocol.strip().lower() == 'rsv1':
        sync_mesh_nodes = _normalize_yn(input_bold("Sync mesh nodes out/in (Y/N) [Y]: "), 'Y')
    ingest_bulletins = _normalize_yn(input_bold("Ingest bulletins in (Y/N) [Y]: "), 'Y')
    ingest_channels = _normalize_yn(input_bold("Ingest channels in (Y/N) [Y]: "), 'Y')
    enabled = _normalize_yn(input_bold("Enabled (Y/N) [Y]: "), 'Y')
    if not bbs_node:
        _finish_action_message("BBS node is required.", "Add Sync Peer")
        return
    if add_sync_peer(
        bbs_node,
        sync_protocol,
        bbs_name,
        sync_bulletins=sync_bulletins,
        sync_mail=sync_mail,
        sync_channels=sync_channels,
        sync_mesh_nodes=sync_mesh_nodes,
        ingest_bulletins=ingest_bulletins,
        ingest_channels=ingest_channels,
        enabled=enabled,
    ):
        _finish_action_message(
            f"Sync peer {bbs_node} added with protocol {sync_protocol}.",
            "Add Sync Peer",
        )
    else:
        _finish_action_message(
            "Could not add sync peer. Check node ID and protocol.",
            "Add Sync Peer",
        )

def edit_sync_peer_entry():
    peer_id = _paginate_select(
        "Edit Sync Peer",
        _sync_peer_lines(get_sync_peers()),
        "No sync peers found.",
        "Enter sync peer ID or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(peer_id):
        return peer_id

    rows = get_sync_peers()
    current = next((row for row in rows if str(row[0]) == peer_id), None)
    if not current:
        _finish_action_message("Sync peer not found.", "Edit Sync Peer")
        return

    begin_form_screen("Edit Sync Peer")
    peer_id = current[0]
    bbs_node = current[1]
    bbs_name = current[2]
    sync_protocol = current[3]
    sync_bulletins = current[5] if len(current) > 5 else 'Y'
    sync_mail = current[6] if len(current) > 6 else 'Y'
    sync_channels = current[7] if len(current) > 7 else 'Y'
    sync_mesh_nodes = current[8] if len(current) > 8 else 'N'
    ingest_bulletins = current[9] if len(current) > 9 else 'Y'
    ingest_channels = current[10] if len(current) > 10 else 'Y'
    enabled = current[13] if len(current) > 13 else 'Y'
    print_bold("Press Enter to keep the current value.")
    bbs_node = input_bold(f"BBS node [{bbs_node}]: ").strip() or bbs_node
    bbs_name = input_bold(f"BBS name [{bbs_name or ''}]: ").strip() or bbs_name
    sync_protocol = input_bold(f"Sync protocol ({'/'.join(SYNC_PROTOCOLS)}) [{sync_protocol}]: ").strip() or sync_protocol
    sync_bulletins = _normalize_yn(
        input_bold(f"Sync bulletins out (Y/N) [{sync_bulletins}]: "),
        sync_bulletins,
    )
    sync_mail = _normalize_yn(
        input_bold(f"Sync mail in/out (Y/N) [{sync_mail}]: "),
        sync_mail,
    )
    sync_channels = _normalize_yn(
        input_bold(f"Sync channels out (Y/N) [{sync_channels}]: "),
        sync_channels,
    )
    if sync_protocol.strip().lower() == 'rsv1':
        sync_mesh_nodes = _normalize_yn(
            input_bold(f"Sync mesh nodes out/in (Y/N) [{sync_mesh_nodes}]: "),
            sync_mesh_nodes,
        )
    else:
        sync_mesh_nodes = 'N'
    ingest_bulletins = _normalize_yn(
        input_bold(f"Ingest bulletins in (Y/N) [{ingest_bulletins}]: "),
        ingest_bulletins,
    )
    ingest_channels = _normalize_yn(
        input_bold(f"Ingest channels in (Y/N) [{ingest_channels}]: "),
        ingest_channels,
    )
    enabled = _normalize_yn(
        input_bold(f"Enabled (Y/N) [{enabled}]: "),
        enabled,
    )
    if update_sync_peer(
        peer_id,
        bbs_node,
        sync_protocol,
        bbs_name,
        sync_bulletins=sync_bulletins,
        sync_mail=sync_mail,
        sync_channels=sync_channels,
        sync_mesh_nodes=sync_mesh_nodes,
        ingest_bulletins=ingest_bulletins,
        ingest_channels=ingest_channels,
        enabled=enabled,
    ):
        _finish_action_message(f"Sync peer {peer_id} updated.", "Edit Sync Peer")
    else:
        _finish_action_message("Could not update sync peer.", "Edit Sync Peer")

def delete_sync_peer_entry():
    peer_id = _paginate_select(
        "Delete Sync Peer",
        _sync_peer_lines(get_sync_peers()),
        "No sync peers found.",
        "Enter sync peer ID or X=cancel:",
        "Deletion cancelled.",
    )
    if _paginate_select_exit(peer_id):
        return peer_id

    if delete_sync_peer(peer_id):
        _finish_action_message(f"Sync peer {peer_id} deleted.", "Delete Sync Peer")
    else:
        _finish_action_message("Sync peer not found.", "Delete Sync Peer")

def _sys_config_lines(rows):
    if not rows:
        return []
    return [
        join_display_fields(
            f"{index}.",
            f"Section: {cfg_section}",
            f"Key: {cfg_key}",
            f"Value: {cfg_value}",
        )
        for index, (cfg_section, cfg_key, cfg_value) in enumerate(rows, 1)
    ]

def list_sys_config():
    paginate_display(
        "List System Configuration",
        _sys_config_lines(get_sys_config_entries()),
        empty_message="No configuration entries found.",
    )
    return False

def add_sys_config_entry_prompt():
    begin_form_screen("Add Configuration Entry")
    cfg_section = input_bold("Section (e.g. bbs, interface): ").strip()
    cfg_key = input_bold("Key: ").strip()
    cfg_value = input_bold("Value: ").strip()
    if not cfg_section or not cfg_key:
        _finish_action_message("Section and key are required.", "Add Configuration Entry")
        return
    if add_sys_config_entry(cfg_section, cfg_key, cfg_value):
        _finish_action_message(
            f"Configuration entry {cfg_section}.{cfg_key} added.",
            "Add Configuration Entry",
        )
    else:
        _finish_action_message(
            "Could not add entry. It may already exist.",
            "Add Configuration Entry",
        )

def edit_sys_config_entry():
    rows = get_sys_config_entries()
    selection = _paginate_select(
        "Edit Configuration Entry",
        _sys_config_lines(rows),
        "No configuration entries found.",
        "Enter row # or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(selection):
        return selection

    try:
        row_index = int(selection) - 1
    except ValueError:
        _finish_action_message("Invalid row number.", "Edit Configuration Entry")
        return

    if row_index < 0 or row_index >= len(rows):
        _finish_action_message("Configuration entry not found.", "Edit Configuration Entry")
        return

    cfg_section, cfg_key, cfg_value = rows[row_index]
    begin_form_screen("Edit Configuration Entry")
    print_bold("Press Enter to keep the current value.")
    cfg_section = input_bold(f"Section [{cfg_section}]: ").strip() or cfg_section
    cfg_key = input_bold(f"Key [{cfg_key}]: ").strip() or cfg_key
    cfg_value = input_bold(f"Value [{cfg_value}]: ").strip() or cfg_value

    if (cfg_section, cfg_key) != (rows[row_index][0], rows[row_index][1]):
        if delete_sys_config_entry(rows[row_index][0], rows[row_index][1]):
            if add_sys_config_entry(cfg_section, cfg_key, cfg_value):
                message = f"Configuration entry updated to {cfg_section}.{cfg_key}."
            else:
                add_sys_config_entry(rows[row_index][0], rows[row_index][1], rows[row_index][2])
                message = "Could not update entry. Section/key may already exist."
        else:
            message = "Could not update entry."
    elif update_sys_config_entry(cfg_section, cfg_key, cfg_value):
        message = f"Configuration entry {cfg_section}.{cfg_key} updated."
    else:
        message = "Configuration entry not found."
    _finish_action_message(message, "Edit Configuration Entry")

def delete_sys_config_entry_prompt():
    rows = get_sys_config_entries()
    selection = _paginate_select(
        "Delete Configuration Entry",
        _sys_config_lines(rows),
        "No configuration entries found.",
        "Enter row # or X=cancel:",
        "Deletion cancelled.",
    )
    if _paginate_select_exit(selection):
        return selection

    try:
        row_index = int(selection) - 1
    except ValueError:
        _finish_action_message("Invalid row number.", "Delete Configuration Entry")
        return

    if row_index < 0 or row_index >= len(rows):
        _finish_action_message("Configuration entry not found.", "Delete Configuration Entry")
        return

    cfg_section, cfg_key, _cfg_value = rows[row_index]
    if delete_sys_config_entry(cfg_section, cfg_key):
        _finish_action_message(
            f"Configuration entry {cfg_section}.{cfg_key} deleted.",
            "Delete Configuration Entry",
        )
    else:
        _finish_action_message("Configuration entry not found.", "Delete Configuration Entry")

def _sysadmin_node_lines(rows):
    if not rows:
        return []
    return [
        join_display_fields(
            f"ID: {node_id}",
            f"Short name: {short_name}",
            f"Node: {node_hex_username}",
        )
        for node_id, short_name, node_hex_username in rows
    ]

def list_sysadmin_nodes():
    paginate_display(
        "List Sysadmin Nodes",
        _sysadmin_node_lines(get_sysadmin_nodes()),
        empty_message="No sysadmin nodes found.",
    )
    return False

def add_sysadmin_node_entry():
    begin_form_screen("Add Sysadmin Node")
    short_name = input_bold("Short name: ").strip()
    node_hex_username = input_bold("Node ID (e.g. !9e9d8704): ").strip()
    if not short_name or not node_hex_username:
        _finish_action_message("Short name and node ID are required.", "Add Sysadmin Node")
        return
    if add_sysadmin_node(short_name, node_hex_username):
        _finish_action_message(
            f"Sysadmin node {short_name} ({node_hex_username}) added.",
            "Add Sysadmin Node",
        )
    else:
        _finish_action_message(
            "Could not add sysadmin node. It may already exist.",
            "Add Sysadmin Node",
        )

def edit_sysadmin_node_entry():
    node_id = _paginate_select(
        "Edit Sysadmin Node",
        _sysadmin_node_lines(get_sysadmin_nodes()),
        "No sysadmin nodes found.",
        "Enter sysadmin ID or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(node_id):
        return node_id

    rows = get_sysadmin_nodes()
    current = next((row for row in rows if str(row[0]) == node_id), None)
    if current is None:
        _finish_action_message("Sysadmin node not found.", "Edit Sysadmin Node")
        return

    begin_form_screen("Edit Sysadmin Node")
    node_id, short_name, node_hex_username = current
    print_bold("Press Enter to keep the current value.")
    short_name = input_bold(f"Short name [{short_name}]: ").strip() or short_name
    node_hex_username = input_bold(f"Node ID [{node_hex_username}]: ").strip() or node_hex_username
    if update_sysadmin_node(node_id, short_name, node_hex_username):
        _finish_action_message(
            f"Sysadmin node {node_id} ({short_name}, {node_hex_username}) updated.",
            "Edit Sysadmin Node",
        )
    else:
        _finish_action_message("Could not update sysadmin node.", "Edit Sysadmin Node")

def delete_sysadmin_node_entry():
    node_id = _paginate_select(
        "Delete Sysadmin Node",
        _sysadmin_node_lines(get_sysadmin_nodes()),
        "No sysadmin nodes found.",
        "Enter sysadmin ID or X=cancel:",
        "Deletion cancelled.",
    )
    if _paginate_select_exit(node_id):
        return node_id

    if delete_sysadmin_node(node_id):
        _finish_action_message(f"Sysadmin node {node_id} deleted.", "Delete Sysadmin Node")
    else:
        _finish_action_message("Sysadmin node not found.", "Delete Sysadmin Node")

def export_sys_config_to_yaml_entry():
    page_title = "Export Configuration to config.yml"
    begin_form_screen(page_title)
    rows = get_sys_config_entries()
    if not rows:
        _finish_action_message("No configuration entries found to export.", page_title)
        return

    confirm = input_bold(
        f"This will overwrite {DEFAULT_CONFIG_FILE}. Continue? (Y/N) [N]: "
    ).strip().upper()
    if confirm != 'Y':
        _finish_action_message("Export cancelled.", page_title)
        return

    output_path = export_sys_config_to_yaml(rows, DEFAULT_CONFIG_FILE)
    _finish_action_message(
        f"Exported {len(rows)} configuration entries to {output_path}.",
        page_title,
    )

def backup_application_entry():
    page_title = "Backup"
    begin_form_screen(page_title)
    try:
        archive_path, file_count, db_count, config_count = create_application_backup()
        _finish_action_message(
            f"Created backup archive backup/{archive_path.name}\n"
            f"       {file_count} file(s): {db_count} SQL dump(s), {config_count} config(s).",
            page_title,
        )
    except (OSError, sqlite3.Error) as exc:
        _finish_action_message(f"Backup failed: {exc}", page_title)

def _reconcile_bulletin_lines(rows):
    return [
        join_display_fields(
            f"ID: {row[0]}",
            f"Board: {row[1]}",
            f"Poster: {row[2]}",
            f"Subject: {row[4]}",
            f"Unique ID: {row[5]}",
        )
        for row in rows
    ]

def review_reconcile_bulletins():
    rows = get_reconcile_bulletins()
    bulletin_id = _paginate_select(
        "Review Reconcile Bulletins",
        _reconcile_bulletin_lines(rows),
        "No bulletins pending reconcile.",
        "Enter bulletin ID or X=cancel:",
        "Reconcile review cancelled.",
    )
    if _paginate_select_exit(bulletin_id):
        return bulletin_id

    begin_form_screen("Review Reconcile Bulletins")
    action = input_bold("[R]estore bulletin [D]elete permanently [X] cancel: ").strip().lower()
    if action == 'x':
        _finish_cancelled("Reconcile review cancelled.", "Review Reconcile Bulletins")
        return
    if action == 'r':
        if restore_reconcile_bulletin(bulletin_id):
            _finish_action_message(f"Bulletin {bulletin_id} restored.", "Review Reconcile Bulletins")
        else:
            _finish_action_message(
                "Bulletin not found or not pending reconcile.",
                "Review Reconcile Bulletins",
            )
    elif action == 'd':
        if confirm_reconcile_bulletin_delete(bulletin_id):
            _finish_action_message(
                f"Bulletin {bulletin_id} permanently deleted.",
                "Review Reconcile Bulletins",
            )
        else:
            _finish_action_message(
                "Bulletin not found or not pending reconcile.",
                "Review Reconcile Bulletins",
            )
    else:
        _finish_action_message("Invalid action.", "Review Reconcile Bulletins")

def _reconcile_channel_lines(rows):
    return [
        join_display_fields(
            f"ID: {row[0]}",
            f"Name: {row[1]}",
            f"Publish: {row[3]}",
            f"Unique ID: {row[4]}",
        )
        for row in rows
    ]

def review_reconcile_channels():
    rows = get_reconcile_channels()
    channel_id = _paginate_select(
        "Review Reconcile Channels",
        _reconcile_channel_lines(rows),
        "No channels pending reconcile.",
        "Enter channel ID or X=cancel:",
        "Reconcile review cancelled.",
    )
    if _paginate_select_exit(channel_id):
        return channel_id

    begin_form_screen("Review Reconcile Channels")
    action = input_bold("[R]estore channel [D]elete permanently [X] cancel: ").strip().lower()
    if action == 'x':
        _finish_cancelled("Reconcile review cancelled.", "Review Reconcile Channels")
        return
    if action == 'r':
        if restore_reconcile_channel(channel_id):
            _finish_action_message(f"Channel {channel_id} restored.", "Review Reconcile Channels")
        else:
            _finish_action_message(
                "Channel not found or not pending reconcile.",
                "Review Reconcile Channels",
            )
    elif action == 'd':
        if confirm_reconcile_channel_delete(channel_id):
            _finish_action_message(
                f"Channel {channel_id} permanently deleted.",
                "Review Reconcile Channels",
            )
        else:
            _finish_action_message(
                "Channel not found or not pending reconcile.",
                "Review Reconcile Channels",
            )
    else:
        _finish_action_message("Invalid action.", "Review Reconcile Channels")

def _unsynced_lines(bulletins, mail_rows, channels):
    total = len(bulletins) + len(mail_rows) + len(channels)
    if total == 0:
        return []

    section_indent = "  "
    entry_indent = "    "
    lines = [f"Unsynced Records ({total} total):"]

    if bulletins:
        lines.append(f"{section_indent}Bulletins:")
        for bulletin in bulletins:
            status = "pending delete sync" if bulletin[4] == 'Y' else "pending sync"
            pending = join_display_fields(*bulletin[6]) if bulletin[6] else "all peers"
            lines.append(
                entry_indent + join_display_fields(
                    f"ID: {bulletin[0]}",
                    f"Board: {bulletin[1]}",
                    f"Poster: {bulletin[2]}",
                    f"Subject: {bulletin[3]}",
                    f"Deleted: {bulletin[4]}",
                    f"Unique ID: {bulletin[5]}",
                    status,
                    f"Pending peers: {pending}",
                )
            )
    else:
        lines.append(f"{section_indent}Bulletins: none")

    if mail_rows:
        lines.append(f"{section_indent}Mail:")
        for mail_row in mail_rows:
            pending = join_display_fields(*mail_row[5]) if mail_row[5] else "all peers"
            lines.append(
                entry_indent + join_display_fields(
                    f"ID: {mail_row[0]}",
                    f"Sender: {mail_row[1]}",
                    f"Recipient: {mail_row[2]}",
                    f"Subject: {mail_row[3]}",
                    f"Unique ID: {mail_row[4]}",
                    f"Pending peers: {pending}",
                )
            )
    else:
        lines.append(f"{section_indent}Mail: none")

    if channels:
        lines.append(f"{section_indent}Channels:")
        for channel in channels:
            pending = join_display_fields(*channel[4]) if channel[4] else "all peers"
            lines.append(
                entry_indent + join_display_fields(
                    f"ID: {channel[0]}",
                    f"Name: {channel[1]}",
                    f"Publish: {channel[2]}",
                    f"Pending peers: {pending}",
                )
            )
    else:
        lines.append(f"{section_indent}Channels: none")

    return lines

def list_unsynced_data():
    bulletins, mail_rows, channels = get_unsynced_records()
    paginate_display(
        "List Unsynced Data",
        _unsynced_lines(bulletins, mail_rows, channels),
        empty_message="No unsynced records found.",
    )
    return False

def _system_status_lines():
    content_lines = _build_system_status_content_lines()
    indent = " " * MENU_OPTION_INDENT
    lines = []
    for line in content_lines:
        if line == "":
            lines.append("")
        elif line in ("Recent connected nodes:",):
            lines.append(line)
        else:
            lines.append(indent + line)
    return lines

def show_system_status():
    paginate_display("System Status", _system_status_lines())
    return False

def run_submenu(menu_name, options, back_label="Main Menu"):
    while True:
        body_lines = [f"{index}. {label}" for index, (label, _) in enumerate(options, 1)]
        body_lines.append(f"0. Back to {back_label}")
        choice = render_menu_screen(menu_name, body_lines)
        clear_screen()
        if choice == '0':
            return
        try:
            option_index = int(choice) - 1
            if 0 <= option_index < len(options):
                result = options[option_index][1]()
                if result is not False:
                    prompt_continue(_lines_used_from_result(result))
            else:
                _finish_action_message("Invalid option. Try again.", menu_name)
                prompt_continue()
        except ValueError:
            _finish_action_message("Invalid option. Try again.", menu_name)
            prompt_continue()


def bulletins_menu():
    run_submenu("Bulletins", [
        ("List Bulletins", list_bulletins),
        ("Add Bulletin", add_bulletin_entry),
        ("Edit Bulletin", edit_bulletin_entry),
        ("Delete Bulletins", delete_bulletin),
        ("Review Reconcile Bulletins", review_reconcile_bulletins),
    ])


def channels_menu():
    run_submenu("Channels", [
        ("List Channels", list_channels),
        ("Add Channel", add_channel_entry),
        ("Edit Channel", edit_channel_entry),
        ("Delete Channels", delete_channel),
        ("Export to CSV", export_channels_csv_entry),
        ("Import from CSV", import_channels_csv_entry),
        ("Review Reconcile Channels", review_reconcile_channels),
    ])


def mail_menu():
    run_submenu("Mail", [
        ("List Mail", list_mail),
        ("Send Mail", send_mail_entry),
        ("Edit Mail", edit_mail_entry),
        ("Delete Mail", delete_mail),
    ])


def sync_peers_menu(back_label="Main Menu"):
    run_submenu("Sync Peers", [
        ("List Sync Peers", list_sync_peers),
        ("Add Sync Peer", add_sync_peer_entry),
        ("Edit Sync Peer", edit_sync_peer_entry),
        ("Delete Sync Peer", delete_sync_peer_entry),
        ("List Unsynced Data", list_unsynced_data),
    ], back_label=back_label)
    return False


def sys_config_menu(back_label="Main Menu"):
    run_submenu("System Configuration", [
        ("List Configuration", list_sys_config),
        ("Add Configuration Entry", add_sys_config_entry_prompt),
        ("Edit Configuration Entry", edit_sys_config_entry),
        ("Delete Configuration Entry", delete_sys_config_entry_prompt),
        ("Export Configuration to config.yml", export_sys_config_to_yaml_entry),
    ], back_label=back_label)
    return False


def core_services_menu(back_label="Administration"):
    while True:
        body_lines = []
        for index, cfg_key in enumerate(CORE_SERVICE_KEYS, 1):
            label = CORE_SERVICE_LABELS[cfg_key]
            state = "Enabled" if is_core_service_enabled(cfg_key) else "Disabled"
            body_lines.append(f"{index}. {label} ({state})")
        body_lines.append("")
        body_lines.append(f"0. Back to {back_label}")
        choice = render_menu_screen("Core Services", body_lines)
        clear_screen()
        if choice == "0":
            return False
        try:
            option_index = int(choice) - 1
            if 0 <= option_index < len(CORE_SERVICE_KEYS):
                toggle_core_service(CORE_SERVICE_KEYS[option_index])
            else:
                _finish_action_message("Invalid option. Try again.", "Core Services")
                prompt_continue()
        except ValueError:
            _finish_action_message("Invalid option. Try again.", "Core Services")
            prompt_continue()


def sysadmin_nodes_menu(back_label="Main Menu"):
    run_submenu("Sysadmin Nodes", [
        ("List Sysadmin Nodes", list_sysadmin_nodes),
        ("Add Sysadmin Node", add_sysadmin_node_entry),
        ("Edit Sysadmin Node", edit_sysadmin_node_entry),
        ("Delete Sysadmin Node", delete_sysadmin_node_entry),
    ], back_label=back_label)
    return False


def administration_menu():
    run_submenu("Administration", [
        ("System Configuration", lambda: sys_config_menu("Administration")),
        ("Core Services", lambda: core_services_menu("Administration")),
        ("Sysadmin Nodes", lambda: sysadmin_nodes_menu("Administration")),
        ("Sync Peers", lambda: sync_peers_menu("Administration")),
        ("Modules", lambda: modules_admin_menu("Administration")),
        ("Backup", backup_application_entry),
    ])


def _module_lines(rows):
    if not rows:
        return []
    lines = []
    for row in rows:
        lines.append(
            join_display_fields(
                f"ID: {row[0]}",
                f"Name: {row[1]}",
                f"Menu: {row[3]}",
            )
        )
        lines.append(
            "  " + join_display_fields(
                f"Dir: {row[2]}",
                f"Enabled: {row[4]}",
                f"Schedule: {row[5]}",
            )
        )
    return lines


def list_modules():
    paginate_display(
        "List Modules",
        _module_lines(get_modules()),
        empty_message="No modules registered.",
    )
    return False


def edit_module_flags_entry():
    rows = get_modules()
    selection = _paginate_select(
        "Edit Module Flags",
        _module_lines(rows),
        "No modules registered.",
        "Enter module ID or X=cancel:",
        "Edit cancelled.",
    )
    if _paginate_select_exit(selection):
        return selection
    current = next((row for row in rows if str(row[0]) == str(selection).strip()), None)
    if current is None:
        _finish_action_message("Module not found.", "Edit Module Flags")
        return
    begin_form_screen("Edit Module Flags")
    enabled = _normalize_yn(input_bold(f"Enabled (Y/N) [{current[4]}]: "), current[4])
    schedule_enabled = _normalize_yn(
        input_bold(f"Schedule enabled (Y/N) [{current[5]}]: "),
        current[5],
    )
    update_module_flags(current[0], enabled=enabled, schedule_enabled=schedule_enabled)
    _finish_action_message(f"Module {current[1]} updated.", "Edit Module Flags")


def run_module_admin(module_dir_name, back_label="Modules"):
    admin_module = load_module_admin(module_dir_name)
    if admin_module is None or not hasattr(admin_module, "run_admin_menu"):
        _finish_action_message("Module admin is not available.", "Modules")
        return False
    admin_module.run_admin_menu(run_submenu, back_label=back_label)
    return False


def modules_admin_menu(back_label="Administration"):
    options = [
        ("List Modules", list_modules),
        ("Edit Module Flags", edit_module_flags_entry),
    ]
    for row in get_modules():
        if row[4] == 'Y' and module_admin_available(row[2]):
            module_dir = row[2]
            module_name = row[1]
            options.append(
                (module_name, lambda module_dir=module_dir: run_module_admin(module_dir, "Modules"))
            )
    run_submenu("Modules", options, back_label=back_label)
    return False


def mesh_nodes_menu(back_label="Main Menu"):
    run_submenu("Mesh Nodes", [
        ("List Mesh Nodes", list_mesh_nodes),
        ("Add Mesh Node", add_mesh_node_entry),
        ("Edit Mesh Node", edit_mesh_node_entry),
        ("Delete Mesh Node", delete_mesh_node_entry),
        ("Export to CSV", export_mesh_nodes_csv_entry),
        ("Import from CSV", import_mesh_nodes_csv_entry),
        ("Purge Mesh Nodes", purge_mesh_nodes_entry),
    ], back_label=back_label)
    return False


def node_catalog_menu(back_label="Main Menu"):
    run_submenu("Node Catalog", [
        ("List Node Catalog", list_node_catalog),
        ("Add Node Catalog Entry", add_node_catalog_entry),
        ("Edit Node Catalog Entry", edit_node_catalog_entry),
        ("Delete Node Catalog Entry", delete_node_catalog_entry),
        ("Export to CSV", export_node_catalog_csv_entry),
        ("Import from CSV", import_node_catalog_csv_entry),
    ], back_label=back_label)
    return False


def _main_menu_body_lines():
    lines = [
        "1. System Status",
        "2. Administration",
    ]
    option_number = 3
    if is_core_bulletins_enabled():
        lines.append(f"{option_number}. Bulletins")
        option_number += 1
    if is_core_channels_enabled():
        lines.append(f"{option_number}. Channels")
        option_number += 1
    if is_core_mail_enabled():
        lines.append(f"{option_number}. Mail")
        option_number += 1
    lines.append("")
    lines.append(f"{option_number}. Node Catalog")
    option_number += 1
    lines.append("")
    lines.append(f"{option_number}. Mesh Nodes")
    lines.append("")
    lines.append("0. Exit")
    return lines


def _main_menu_actions():
    actions = {
        "1": show_system_status,
        "2": administration_menu,
        "0": None,
    }
    option_number = 3
    if is_core_bulletins_enabled():
        actions[str(option_number)] = bulletins_menu
        option_number += 1
    if is_core_channels_enabled():
        actions[str(option_number)] = channels_menu
        option_number += 1
    if is_core_mail_enabled():
        actions[str(option_number)] = mail_menu
        option_number += 1
    actions[str(option_number)] = node_catalog_menu
    option_number += 1
    actions[str(option_number)] = mesh_nodes_menu
    return actions


def display_main_menu():
    return render_menu_screen("Main Menu", _main_menu_body_lines())

def input_select_row(prompt):
    console.print()
    return input_bold(prompt)

def _finish_action_message(message, page_title):
    clear_screen()
    begin_data_display(page_title)
    message_lines = message.splitlines() or [""]
    for line in message_lines:
        _print_no_data(line)
    lines_used = PAGE_HEADER_LINE_COUNT + len(message_lines)
    _pad_to_line(MENU_SEPARATOR_LINE, lines_used)
    print_separator()

def _finish_cancelled(message, page_title):
    _finish_action_message(message, page_title)

def prompt_continue(lines_used=None, message="Press Enter to continue..."):
    if lines_used is not None:
        _prompt_at_bottom(lines_used, message)
    else:
        input_bold(message)
    clear_screen()

def _lines_used_from_result(result):
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        return result[1]
    return None

def main():
    require_config_file()
    clear_screen()
    initialize_database(quiet=True)
    ensure_sys_config_from_yaml()
    ensure_core_services_config()
    backfill_sync_peer_last_heard()
    show_splash_screen()
    while True:
        choice = display_main_menu()
        clear_screen()
        if choice == '0':
            break
        action = _main_menu_actions().get(choice)
        if action is None:
            _finish_action_message("Invalid option. Try again.", "Main Menu")
            prompt_continue()
            continue
        action()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{APP_NAME} admin")
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"{APP_NAME} {VERSION}",
    )
    parser.parse_args()
    main()
