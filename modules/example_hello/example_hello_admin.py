from rsmesh_bbs import admin_ui
from example_hello import storage


def list_visits():
    admin_ui.paginate_display(
        "Example Hello Visits",
        storage.list_visit_lines(),
        empty_message="No visits recorded.",
    )
    return False


def run_admin_menu(run_submenu, back_label="Modules"):
    run_submenu(
        "Example Hello",
        [
            ("List Visits", list_visits),
        ],
        back_label=back_label,
    )
    return False
