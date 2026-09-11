import pytest

from rsmesh_bbs import db_operations
from rsmesh_bbs.mesh_client import BbsMeshClient
from rsmesh_bbs.utils import user_states


def _close_db_connection():
    if hasattr(db_operations.thread_local, "connection"):
        db_operations.thread_local.connection.close()
        del db_operations.thread_local.connection


@pytest.fixture(autouse=True)
def mesh_ui_dir(monkeypatch, tmp_path):
    """Keep generated mesh UI files out of the project tree during tests."""
    ui_dir = tmp_path / "mesh_ui"
    monkeypatch.setattr("rsmesh_bbs.mesh_ui.MESH_UI_DIR", ui_dir)
    monkeypatch.setattr("rsmesh_bbs.mesh_ui.MAIN_MENU_FILE", ui_dir / "main_menu.txt")
    monkeypatch.setattr("rsmesh_bbs.mesh_ui.MAIN_MENU_OLD_FILE", ui_dir / "main_menu.old")


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """Point db_operations at a fresh SQLite file under pytest's tmp_path."""
    db_path = tmp_path / "test-rsmesh-bbs.db"
    monkeypatch.setattr(db_operations, "BBS_DB_FILE", str(db_path))
    _close_db_connection()
    db_operations.initialize_database(quiet=True)
    yield db_path
    _close_db_connection()


@pytest.fixture
def mesh_client(temp_db, monkeypatch):
    """In-process mesh handset against a temp database (no radio)."""
    monkeypatch.setattr(
        "rsmesh_bbs.command_handlers.get_board_name",
        lambda config_file=None: "Test BBS",
    )
    monkeypatch.setattr("rsmesh_bbs.utils.time.sleep", lambda *_args, **_kwargs: None)
    user_states.clear()
    client = BbsMeshClient.create()
    yield client
    user_states.clear()
