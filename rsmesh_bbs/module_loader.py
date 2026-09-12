import sys
import importlib.util
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from .db_operations import get_modules, get_module_by_id

APP_ROOT = Path(__file__).resolve().parent.parent
MODULES_DIR = APP_ROOT / "modules"

MODULE_RESULT_CONTINUE = "continue"
MODULE_RESULT_EXIT = "exit"


@dataclass
class ScheduleTask:
    module_id: int
    name: str
    interval_minutes: int
    callback: object
    last_run: float = 0.0


class ModuleContext:
    def __init__(self, module_row, interface=None, manager=None):
        self.id = module_row[0]
        self.module_name = module_row[1]
        self.module_dir_name = module_row[2]
        self.menu_option = module_row[3]
        self.enabled = module_row[4]
        self.schedule_enabled = module_row[5]
        self.main_menu_visible = module_row[6] if len(module_row) > 6 else "N"
        self.interface = interface
        self._manager = manager

    @property
    def module_dir(self):
        return MODULES_DIR / self.module_dir_name

    def path(self, *parts):
        return self.module_dir.joinpath(*parts)

    def send(self, sender_id, text):
        """Send a single short prompt (minimal pacing). Prefer send_user_message(s)."""
        from .utils import send_message
        send_message(text, sender_id, self.interface)

    def send_user_message(self, sender_id, text):
        from .utils import send_user_message
        send_user_message(text, sender_id, self.interface)

    def send_user_messages(self, sender_id, messages):
        from .utils import send_user_messages
        send_user_messages(messages, sender_id, self.interface)

    def send_bundled(self, sender_id, lines, trailing_message=None):
        from .utils import bundle_lines_for_mesh, send_user_messages
        messages = bundle_lines_for_mesh(lines)
        if trailing_message:
            messages.append(trailing_message)
        send_user_messages(messages, sender_id, self.interface)

    def enqueue_send(self, sender_id, text):
        """Queue a paced user message for delivery on the pubsub thread."""
        from .utils import enqueue_user_messages
        enqueue_user_messages([text], sender_id, self.interface)

    def enqueue_send_messages(self, sender_id, messages):
        """Queue paced user messages for delivery on the pubsub thread."""
        from .utils import enqueue_user_messages
        enqueue_user_messages(messages, sender_id, self.interface)

    def is_sysadmin(self, sender_id):
        from .command_handlers import is_sysadmin
        return is_sysadmin(sender_id, self.interface)

    def register_service(self, name, service):
        if self._manager is not None:
            self._manager.register_service(name, service)

    def register_schedule(self, name, interval_minutes, callback):
        if self._manager is not None:
            self._manager.register_schedule(self.id, name, interval_minutes, callback)


class ModuleManager:
    def __init__(self):
        self._instances = {}
        self._services = {}
        self._schedules = []

    def register_service(self, name, service):
        self._services[name] = service

    def get_service(self, name):
        return self._services.get(name)

    def register_schedule(self, module_id, name, interval_minutes, callback):
        self._schedules.append(
            ScheduleTask(int(module_id), name, int(interval_minutes), callback)
        )

    def load_modules(self, interface=None):
        self._instances.clear()
        self._services.clear()
        self._schedules.clear()
        for row in get_modules(enabled_only=False):
            instance = self._load_module_instance(row)
            if instance is None:
                continue
            self._instances[row[0]] = (row, instance)
            if row[4] == 'Y':
                try:
                    ctx = ModuleContext(row, interface=interface, manager=self)
                    instance.on_load(ctx)
                except Exception as exc:
                    logging.error("Failed to load module %s: %s", row[2], exc)

    def _load_module_instance(self, row):
        module_dir = row[2]
        module_path = MODULES_DIR / module_dir / "module.py"
        if not module_path.exists():
            logging.warning("Module file missing: %s", module_path)
            return None
        try:
            if str(MODULES_DIR) not in sys.path:
                sys.path.insert(0, str(MODULES_DIR))
            spec = importlib.util.spec_from_file_location(f"bbs_module.{module_dir}", module_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not hasattr(module, "Module"):
                logging.warning("Module %s has no Module class", module_dir)
                return None
            return module.Module()
        except Exception as exc:
            logging.error("Error importing module %s: %s", module_dir, exc)
            return None

    def get_menu_modules(self):
        from .mesh_ui import enabled_modules_for_submenu

        submenu_ids = {row[0] for row in enabled_modules_for_submenu()}
        modules = []
        for row, _instance in self._instances.values():
            if row[0] not in submenu_ids:
                continue
            modules.append({
                'id': row[0],
                'module_name': row[1],
                'menu_option': row[3],
            })
        return sorted(modules, key=lambda item: item['module_name'].lower())

    def get_by_menu_option(self, menu_option):
        menu_option = (menu_option or '').strip().lower()
        if not menu_option:
            return None
        for row, instance in self._instances.values():
            if row[4] == 'Y' and (row[3] or '').lower() == menu_option:
                return row, instance
        return None

    def get_by_id(self, module_id):
        try:
            module_id = int(module_id)
        except (TypeError, ValueError):
            return None, None
        entry = self._instances.get(module_id)
        if entry is None:
            row = get_module_by_id(module_id)
            if row is None:
                return None, None
            instance = self._load_module_instance(row)
            if instance is None:
                return None, None
            self._instances[row[0]] = (row, instance)
            return row, instance
        return entry

    @staticmethod
    def _format_module_menu_line(module_name, menu_option):
        option = (menu_option or '?')[:1].lower()
        name = module_name or ''
        for index, char in enumerate(name):
            if char.lower() == option:
                bracketed = option.upper()
                return f"{name[:index]}[{bracketed}]{name[index + 1:]}"
        return f"[{option.upper()}]{name}"

    def build_modules_menu_text(self):
        modules = self.get_menu_modules()
        if not modules:
            return "= Modules =\nNo modules are enabled."
        lines = ["= Modules =", "Select:"]
        for module in modules:
            lines.append(self._format_module_menu_line(module['module_name'], module['menu_option']))
        lines.append("E[X]IT")
        return "\n".join(lines)

    def on_module_enter(self, module_id, sender_id, interface):
        row, instance = self.get_by_id(module_id)
        if row is None or instance is None or row[4] != 'Y':
            return False
        ctx = ModuleContext(row, interface=interface, manager=self)
        instance.on_enter(sender_id, ctx)
        from .utils import update_user_state
        update_user_state(sender_id, {"command": "MODULE", "module_id": row[0], "step": 1})
        return True

    def on_module_message(self, module_id, sender_id, message, interface):
        row, instance = self.get_by_id(module_id)
        if row is None or instance is None:
            return MODULE_RESULT_EXIT
        ctx = ModuleContext(row, interface=interface, manager=self)
        try:
            return instance.on_message(sender_id, message, ctx) or MODULE_RESULT_EXIT
        except Exception as exc:
            logging.error("Module %s message handler failed: %s", row[2], exc)
            ctx.send_user_message(sender_id, "Module error. Returning to main menu.")
            return MODULE_RESULT_EXIT

    def run_due_schedules(self, interface):
        now = time.time()
        for task in self._schedules:
            row = get_module_by_id(task.module_id)
            if row is None or row[4] != 'Y' or row[5] != 'Y':
                continue
            if task.last_run and (now - task.last_run) < task.interval_minutes * 60:
                continue
            ctx = ModuleContext(row, interface=interface, manager=self)
            try:
                task.callback(ctx)
            except Exception as exc:
                logging.error(
                    "Scheduled task %s for module %s failed: %s",
                    task.name, row[2], exc,
                )
            task.last_run = now


def load_module_admin(module_dir_name):
    admin_path = MODULES_DIR / module_dir_name / f"{module_dir_name}_admin.py"
    if not admin_path.exists():
        return None
    try:
        if str(MODULES_DIR) not in sys.path:
            sys.path.insert(0, str(MODULES_DIR))
        spec = importlib.util.spec_from_file_location(
            f"bbs_module.{module_dir_name}_admin", admin_path
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        logging.error("Error loading module admin %s: %s", module_dir_name, exc)
        return None


def module_admin_available(module_dir_name):
    return (MODULES_DIR / module_dir_name / f"{module_dir_name}_admin.py").exists()
