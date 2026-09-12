"""Mesh user interface assets (cached main menu body)."""

import shutil
from contextlib import contextmanager
from pathlib import Path

from .config_init import get_board_name, parse_config_value
from .core_services import (
    CORE_MENU_LETTERS,
    is_core_mail_enabled,
    is_core_service_enabled,
    is_mail_commands_on_main_menu,
)
from .db_operations import add_sys_config_entry, get_modules, get_sys_config_value, update_sys_config_entry
from .module_loader import APP_ROOT, ModuleManager
from .utils import MESH_MESSAGE_MAX_SIZE

MESH_UI_DIR = APP_ROOT / "mesh_ui"
MAIN_MENU_FILE = MESH_UI_DIR / "main_menu.txt"
MAIN_MENU_OLD_FILE = MESH_UI_DIR / "main_menu.old"

CFG_SECTION = "bbs"
SUPPRESS_MODULES_MENU_KEY = "suppress_modules_menu"

MENU_LABELS = {
    "B": "[B]ulletins",
    "C": "[C]hannels",
    "M": "[M]ail",
    "O": "M[o]dules",
    "X": "E[X]IT",
}

MAIL_SUBMENU_TEXT = "= Mail =\n[R]ead Mail  [S]end Mail"
MAIL_MAIN_MENU_LABELS = {
    "R": "[R]ead Mail",
    "S": "[S]end Mail",
}

_WORST_CASE_MAIL_COUNT = 999
_WORST_CASE_BOARD_NAME = "X" * 40

_main_menu_regen_defer_depth = 0
_main_menu_regen_pending = False


def is_suppress_modules_menu():
    value = get_sys_config_value(CFG_SECTION, SUPPRESS_MODULES_MENU_KEY)
    if value is None:
        return False
    return parse_config_value(value) is True


def set_suppress_modules_menu(enabled):
    value = "true" if enabled else "false"
    if get_sys_config_value(CFG_SECTION, SUPPRESS_MODULES_MENU_KEY) is None:
        add_sys_config_entry(CFG_SECTION, SUPPRESS_MODULES_MENU_KEY, value)
    else:
        update_sys_config_entry(CFG_SECTION, SUPPRESS_MODULES_MENU_KEY, value)
    request_main_menu_regeneration()


def _enabled_modules_missing_from_main_menu():
    on_main_ids = {row[0] for row in _modules_on_main_menu()}
    return [row for row in _enabled_modules() if row[0] not in on_main_ids]


def validate_enable_suppress_modules_menu():
    """Return whether Suppress Modules Submenu can be turned on."""
    missing = _enabled_modules_missing_from_main_menu()
    if not missing:
        return True, ""
    names = ", ".join(row[1] for row in missing)
    return False, (
        "Cannot enable Suppress Modules Submenu: enabled module(s) are not on the main menu "
        f"({names}). Set Show on main menu to Y for each enabled module, or disable them."
    )


def toggle_suppress_modules_menu():
    if is_suppress_modules_menu():
        set_suppress_modules_menu(False)
        return True, ""
    ok, message = validate_enable_suppress_modules_menu()
    if not ok:
        return False, message
    set_suppress_modules_menu(True)
    return True, ""


def request_main_menu_regeneration():
    """Refresh the cached menu now, or after a deferred admin session ends."""
    global _main_menu_regen_pending
    if _main_menu_regen_defer_depth > 0:
        _main_menu_regen_pending = True
        return
    regenerate_main_menu_file()


@contextmanager
def defer_main_menu_regeneration():
    """Batch menu rewrites until the caller exits (e.g. Administration menu)."""
    global _main_menu_regen_defer_depth, _main_menu_regen_pending
    _main_menu_regen_defer_depth += 1
    try:
        yield
    finally:
        _main_menu_regen_defer_depth -= 1
        if _main_menu_regen_defer_depth == 0 and _main_menu_regen_pending:
            regenerate_main_menu_file()


def ensure_menu_config():
    """Seed main-menu sys_config keys and refresh the cached menu body.

    Called after startup config is loaded (ensure_core_services_config) — not from
    initialize_database(). Runtime toggles use request_main_menu_regeneration().
    """
    if get_sys_config_value(CFG_SECTION, SUPPRESS_MODULES_MENU_KEY) is None:
        add_sys_config_entry(CFG_SECTION, SUPPRESS_MODULES_MENU_KEY, "false")
    regenerate_main_menu_file()


def _enabled_modules():
    return [row for row in get_modules(enabled_only=True) if row[4] == "Y"]


def _modules_on_main_menu():
    """Enabled modules shown on the main menu (promoted or using a freed core letter)."""
    rows = []
    for row in _enabled_modules():
        option = (row[3] or "").upper()
        if row[6] == "Y":
            rows.append(row)
            continue
        for letter, cfg_key in CORE_MENU_LETTERS:
            if option == letter and not is_core_service_enabled(cfg_key):
                rows.append(row)
                break
    return rows


def _all_enabled_modules_on_main_menu():
    enabled = _enabled_modules()
    return bool(enabled) and all(row[6] == "Y" for row in enabled)


def enabled_modules_for_submenu():
    """Enabled modules that would appear under M[o]dules."""
    enabled = _enabled_modules()
    if is_suppress_modules_menu():
        return [row for row in enabled if row[6] != "Y"]
    return enabled


def should_show_modules_entry():
    """Whether M[o]dules appears on the mesh main menu.

    Never shown when there are no enabled modules (suppress setting is ignored).
    With suppress on, hidden when every enabled module is already on the main menu.
    """
    enabled = _enabled_modules()
    if not enabled:
        return False
    if is_suppress_modules_menu():
        return not _all_enabled_modules_on_main_menu()
    return True


def get_main_menu_keys():
    keys = {"X"}
    for letter, cfg_key in CORE_MENU_LETTERS:
        if letter == "M" and is_core_mail_enabled():
            if is_mail_commands_on_main_menu():
                keys.update(MAIL_MAIN_MENU_LABELS.keys())
            else:
                keys.add("M")
        elif is_core_service_enabled(cfg_key):
            keys.add(letter)
    if should_show_modules_entry():
        keys.add("O")
    for row in _modules_on_main_menu():
        keys.add((row[3] or "").upper())
    return keys


def _format_module_label(module_name, menu_option):
    return ModuleManager._format_module_menu_line(module_name, menu_option)


def _format_two_column(labels):
    if not labels:
        return []
    width = max(len(label) for label in labels)
    lines = []
    index = 0
    while index < len(labels):
        left = labels[index]
        right = labels[index + 1] if index + 1 < len(labels) else None
        if right is not None:
            lines.append(f"{left:<{width}} {right}")
            index += 2
        else:
            lines.append(left)
            index += 1
    return lines


def build_main_menu_body():
    """Build cached main-menu option rows (no title line)."""
    row_groups = []

    core_row = []
    for letter, cfg_key in CORE_MENU_LETTERS:
        if letter in ("B", "C") and is_core_service_enabled(cfg_key):
            core_row.append(MENU_LABELS[letter])
    if core_row:
        row_groups.append(core_row)

    module_labels = [
        _format_module_label(row[1], row[3])
        for row in sorted(_modules_on_main_menu(), key=lambda item: item[1].lower())
    ]
    while module_labels:
        row_groups.append(module_labels[:2])
        module_labels = module_labels[2:]

    service_row = []
    if is_core_mail_enabled():
        if is_mail_commands_on_main_menu():
            service_row.extend(MAIL_MAIN_MENU_LABELS[letter] for letter in ("R", "S"))
        else:
            service_row.append(MENU_LABELS["M"])
    if should_show_modules_entry():
        service_row.append(MENU_LABELS["O"])
    if service_row:
        row_groups.append(service_row)

    row_groups.append([MENU_LABELS["X"]])

    lines = []
    for group in row_groups:
        lines.extend(_format_two_column(group))
    return "\n".join(lines) + ("\n" if lines else "")


def _main_menu_title(board_name=None, mail_count=_WORST_CASE_MAIL_COUNT):
    if board_name is None:
        try:
            board_name = get_board_name()
        except FileNotFoundError:
            board_name = "RSNetwork BBS"
    return f"= {board_name} : {mail_count} Msg(s) ="


def _validation_title(board_name=None):
    if board_name is None:
        board_name = _WORST_CASE_BOARD_NAME
    return _main_menu_title(board_name=board_name, mail_count=_WORST_CASE_MAIL_COUNT)


def _combined_main_menu_size(body, board_name=None):
    title = _validation_title(board_name=board_name)
    combined = f"{title}\n{body.rstrip()}\n"
    return len(combined.encode("utf-8"))


def _validate_cached_main_menu_body(text, board_name=None):
    if not text or not text.strip():
        return False
    body = text if text.endswith("\n") else text + "\n"
    return _combined_main_menu_size(body, board_name=board_name) <= MESH_MESSAGE_MAX_SIZE


def load_main_menu_body(board_name=None):
    """Read cached main menu body, falling back to a fresh build when invalid."""
    try:
        if MAIN_MENU_FILE.is_file():
            text = MAIN_MENU_FILE.read_text(encoding="utf-8")
            if _validate_cached_main_menu_body(text, board_name=board_name):
                return text if text.endswith("\n") else text + "\n"
    except OSError:
        pass
    return build_main_menu_body()


def regenerate_main_menu_file():
    """Rewrite mesh_ui/main_menu.txt from current configuration."""
    global _main_menu_regen_pending
    _main_menu_regen_pending = False
    MESH_UI_DIR.mkdir(parents=True, exist_ok=True)
    body = build_main_menu_body()
    if MAIN_MENU_FILE.is_file():
        shutil.copy2(MAIN_MENU_FILE, MAIN_MENU_OLD_FILE)
    MAIN_MENU_FILE.write_text(body, encoding="utf-8")
    return str(MAIN_MENU_FILE)
