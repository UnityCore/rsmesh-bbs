"""Mesh user interface assets (cached main menu body)."""

import shutil
from pathlib import Path

from .core_services import is_core_mail_enabled
from .module_loader import APP_ROOT

MESH_UI_DIR = APP_ROOT / "mesh_ui"
MAIN_MENU_FILE = MESH_UI_DIR / "main_menu.txt"
MAIN_MENU_OLD_FILE = MESH_UI_DIR / "main_menu.old"

MENU_LABELS = {
    "B": "[B]ulletins",
    "C": "[C]hannels",
    "M": "[M]ail",
    "O": "M[o]dules",
    "X": "E[X]IT",
}

MENU_ROWS = (
    ("B", "C"),
    ("M", "O"),
    ("X", None),
)

MENU_LEFT_WIDTH = max(
    len(MENU_LABELS[left])
    for left, right in MENU_ROWS
    if left in MENU_LABELS
)

MAIN_MENU_KEYS_BASE = frozenset({"B", "C", "M", "O", "X"})

MAIL_SUBMENU_TEXT = "= Mail =\n[R]ead Mail  [S]end Mail"


def get_main_menu_keys():
    keys = set(MAIN_MENU_KEYS_BASE)
    if not is_core_mail_enabled():
        keys.discard("M")
    return keys


def build_main_menu_body():
    """Build cached main-menu option rows (no title line)."""
    enabled = get_main_menu_keys()
    lines = []
    for left_key, right_key in MENU_ROWS:
        left_label = MENU_LABELS[left_key] if left_key in enabled else None
        right_label = (
            MENU_LABELS[right_key]
            if right_key is not None and right_key in enabled
            else None
        )
        if left_label and right_label:
            lines.append(f"{left_label:<{MENU_LEFT_WIDTH}} {right_label}")
        elif left_label:
            lines.append(left_label)
        elif right_label:
            lines.append(right_label)
    return "\n".join(lines) + ("\n" if lines else "")


def load_main_menu_body():
    """Read cached main menu body, falling back to a fresh build."""
    try:
        if MAIN_MENU_FILE.is_file():
            text = MAIN_MENU_FILE.read_text(encoding="utf-8")
            if text.strip():
                return text if text.endswith("\n") else text + "\n"
    except OSError:
        pass
    return build_main_menu_body()


def regenerate_main_menu_file():
    """Rewrite mesh_ui/main_menu.txt from current core-service toggles."""
    MESH_UI_DIR.mkdir(parents=True, exist_ok=True)
    body = build_main_menu_body()
    if MAIN_MENU_FILE.is_file():
        shutil.copy2(MAIN_MENU_FILE, MAIN_MENU_OLD_FILE)
    MAIN_MENU_FILE.write_text(body, encoding="utf-8")
    return str(MAIN_MENU_FILE)
