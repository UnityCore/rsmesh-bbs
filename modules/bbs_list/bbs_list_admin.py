from rsmesh_bbs import admin_ui
from rsmesh_bbs.bbs_info import get_bbs_info

from bbs_list import module as bbs_list_module
from bbs_list import storage


def _normalize_yn(value, default="N"):
    text = (value or default).strip().upper()
    return "Y" if text == "Y" else "N"


def list_entries():
    admin_ui.paginate_display(
        "BBS List Entries",
        storage.format_admin_lines(sync_only=False),
        empty_message="No BBS entries.",
    )
    return False


def list_sync_interested():
    admin_ui.paginate_display(
        "BBS List : Sync Interested",
        storage.format_admin_lines(sync_only=True),
        empty_message="No boards marked sync interested.",
    )
    return False


def add_entry():
    admin_ui.begin_form_screen("BBS List : Add Entry")
    board_name = admin_ui.input_bold("Board name: ").strip()
    node_hex = admin_ui.input_bold("Node hex ID (e.g. !9e9d8704): ").strip()
    short_name = admin_ui.input_bold("Short name (4 chars): ").strip()
    location = admin_ui.input_bold("Location (optional): ").strip()
    sync_interest = _normalize_yn(
        admin_ui.input_bold("Interested in sync arrangements (Y/N) [N]: "),
        "N",
    )
    if not board_name or not node_hex or not short_name:
        admin_ui.finish_action_message(
            "Board name, node hex ID, and short name are required.",
            "BBS List : Add Entry",
        )
        return
    if not storage.upsert_entry(
        board_name,
        node_hex,
        short_name,
        location=location,
        sync_interest=sync_interest,
        is_local="Y",
    ):
        admin_ui.finish_action_message("Could not add BBS entry.", "BBS List : Add Entry")
        return
    bbs_list_module.queue_entry_sync(node_hex)
    admin_ui.finish_action_message(f"BBS entry {board_name} added.", "BBS List : Add Entry")


def register_this_bbs():
    admin_ui.begin_form_screen("BBS List : Register This BBS")
    info = get_bbs_info()
    board_name = info.board_name
    node_default = info.node_id or ""
    short_default = info.short_name or ""
    node_hex = admin_ui.input_bold(f"Node hex ID for this BBS [{node_default}]: ").strip() or node_default
    short_name = admin_ui.input_bold(f"Short name (4 chars) [{short_default}]: ").strip() or short_default
    location = admin_ui.input_bold("Location (optional): ").strip()
    sync_interest = _normalize_yn(
        admin_ui.input_bold("Interested in sync arrangements (Y/N) [Y]: "),
        "Y",
    )
    if not node_hex or not short_name:
        admin_ui.finish_action_message(
            "Node hex ID and short name are required.",
            "BBS List : Register This BBS",
        )
        return
    if not storage.upsert_entry(
        board_name,
        node_hex,
        short_name,
        location=location,
        sync_interest=sync_interest,
        is_local="Y",
    ):
        admin_ui.finish_action_message(
            "Could not register this BBS.",
            "BBS List : Register This BBS",
        )
        return
    bbs_list_module.queue_entry_sync(node_hex)
    admin_ui.finish_action_message(
        f"This BBS ({board_name}) registered in the directory.",
        "BBS List : Register This BBS",
    )


def edit_entry():
    rows = storage.list_entries()
    if not rows:
        admin_ui.paginate_display("BBS List : Edit Entry", [], empty_message="No BBS entries.")
        return False

    admin_ui.begin_form_screen("BBS List : Edit Entry")
    node_hex = admin_ui.input_bold("Node hex ID to edit: ").strip()
    entry = storage.get_entry(node_hex)
    if entry is None:
        admin_ui.finish_action_message("BBS entry not found.", "BBS List : Edit Entry")
        return

    board_name = admin_ui.input_bold(f"Board name [{entry['board_name']}]: ").strip()
    short_name = admin_ui.input_bold(f"Short name [{entry['short_name']}]: ").strip()
    location = admin_ui.input_bold(f"Location [{entry['location'] or ''}]: ").strip()
    sync_interest = _normalize_yn(
        admin_ui.input_bold(f"Sync interest (Y/N) [{entry['sync_interest']}]: "),
        entry["sync_interest"],
    )
    if not storage.upsert_entry(
        board_name or entry["board_name"],
        entry["node_hex"],
        short_name or entry["short_name"],
        location=location if location else entry["location"],
        sync_interest=sync_interest,
        is_local=entry["is_local"],
    ):
        admin_ui.finish_action_message("Could not update BBS entry.", "BBS List : Edit Entry")
        return
    bbs_list_module.queue_entry_sync(entry["node_hex"])
    admin_ui.finish_action_message(
        f"BBS entry {entry['node_hex']} updated.",
        "BBS List : Edit Entry",
    )


def delete_entry():
    admin_ui.begin_form_screen("BBS List : Delete Entry")
    node_hex = admin_ui.input_bold("Node hex ID to delete: ").strip()
    if not storage.delete_entry(node_hex):
        admin_ui.finish_action_message("BBS entry not found.", "BBS List : Delete Entry")
        return
    admin_ui.finish_action_message(
        f"BBS entry {storage.normalize_node_hex(node_hex)} deleted.",
        "BBS List : Delete Entry",
    )


def run_admin_menu(run_submenu, back_label="Modules"):
    run_submenu(
        "BBS List",
        [
            ("List Entries", list_entries),
            ("List Sync Interested", list_sync_interested),
            ("Register This BBS", register_this_bbs),
            ("Add Entry", add_entry),
            ("Edit Entry", edit_entry),
            ("Delete Entry", delete_entry),
        ],
        back_label=back_label,
    )
    return False
