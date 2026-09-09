from rsmesh_bbs import admin_ui
from node_info import storage


def list_node_info():
    lines = storage.format_admin_node_detail_lines()
    if lines == ["No nodes in database."]:
        admin_ui.paginate_display("List Node Info", [], empty_message="No nodes in database.")
    else:
        admin_ui.paginate_display("List Node Info", lines)
    return False


def run_admin_menu(run_submenu, back_label="Modules"):
    run_submenu(
        "Node Info",
        [
            ("List Node Info", list_node_info),
        ],
        back_label=back_label,
    )
    return False
