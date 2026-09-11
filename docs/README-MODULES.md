# RSMesh BBS Modules

Release 1.1

Modules extend the mesh BBS with optional menus, scheduled tasks, and shared services. Each module lives in its own subdirectory under `modules/`.

## Directory layout

```
modules/
  my_module/
    module.py          # Required: Module class
    config.yml         # Optional: module settings
    my_module_admin.py # Optional: SysAdmin UI hooks
    storage.py         # Optional: data/helpers
```

Enable modules in the SysAdmin **Modules** menu. Mesh users open the module list from the main menu with **M[o]dules** (`O`). Each enabled module appears there using its configured menu option letter. When a core service is disabled, its main-menu key (`B`, `C`, or `M`) can be claimed by a module instead.

## Module class

Implement a `Module` class in `module.py`:

```python
from rsmesh_bbs.module_loader import MODULE_RESULT_CONTINUE, MODULE_RESULT_EXIT


class Module:
    def on_load(self, ctx):
        """Called once when the module is enabled at server startup."""

    def on_enter(self, sender_id, ctx):
        """Called when a mesh user selects this module from the Modules menu."""

    def on_message(self, sender_id, message, ctx):
        """Handle mesh user input while inside this module."""
        return MODULE_RESULT_CONTINUE  # or MODULE_RESULT_EXIT
```

Return `MODULE_RESULT_EXIT` when the user should return to the main menu (for example after `x`). The server also treats `x` as exit before your handler runs.

## ModuleContext (`ctx`)

| Method | Use when |
|--------|----------|
| `ctx.send(sender_id, text)` | Short, single-shot prompts where ordering does not matter. Minimal pacing. |
| `ctx.send_user_message(sender_id, text)` | One user-facing reply with mesh pacing. **Preferred for most UI.** |
| `ctx.send_user_messages(sender_id, messages)` | Several messages that must arrive in order (for example stats, then menu). **Preferred for content + follow-up prompt.** |
| `ctx.send_bundled(sender_id, lines, trailing_message=None)` | Long line-oriented output split into 200-character mesh bundles, with optional final message (for example a menu). |
| `ctx.enqueue_send(sender_id, text)` | Queue a paced message from a **scheduled task** (see below). |
| `ctx.enqueue_send_messages(sender_id, messages)` | Queue a paced message sequence from a scheduled task. |
| `ctx.is_sysadmin(sender_id)` | True if the sender is a configured sysadmin node. |
| `ctx.path(*parts)` | Path inside the module directory (for databases, config files). |
| `ctx.register_service(name, service)` | Register a shared object other code can look up. |
| `ctx.register_schedule(name, minutes, callback)` | Run `callback(ctx)` on an interval while the module is enabled. |

### Sending mesh messages safely

Mesh sends must run on the **pubsub receive thread**. Calling `ctx.send*` from `on_enter` or `on_message` is safe because those run on that thread.

**Scheduled tasks** (`register_schedule`) run on a background worker thread. Do **not** call `ctx.send` or `ctx.send_user_message` from a schedule callback — use `ctx.enqueue_send` or `ctx.enqueue_send_messages` instead. The server drains the queue on incoming packets and once per second in its main loop.

### Ordering content and menus

When you show variable-length content followed by a menu or prompt, send them as **one paced sequence**:

```python
menu = "= My Module =\nSelect:\n[A]ction\nE[X]IT"
ctx.send_user_messages(sender_id, [report_text, menu])
```

For long line lists:

```python
ctx.send_bundled(sender_id, ["= Report =", line1, line2, ...], trailing_message=menu)
```

Avoid calling `ctx.send` for content and then `ctx.send` again for the menu — bundles can arrive out of order on the mesh.

## Scheduled tasks

```python
def on_load(self, ctx):
    ctx.register_schedule("hourly_task", 60, self._hourly)

def _hourly(self, ctx):
    for sender_id in storage.pending_notify():
        ctx.enqueue_send(sender_id, "Scheduled hello!")
```

Interval is in **minutes**. Tasks run only while the module is enabled and schedule is enabled in SysAdmin.

## Optional admin UI

Add `{module_dir}_admin.py` beside `module.py` (for example `modules/node_info/node_info_admin.py`). The SysAdmin app loads it when the module is enabled and the file exists.

### Admin module contract

Export `run_admin_menu(run_submenu, back_label="Modules")`. The core admin passes its submenu runner so your module can register actions:

```python
from rsmesh_bbs import admin_ui


def list_items():
    admin_ui.paginate_display("My Items", lines, empty_message="No items found.")
    return False


def run_admin_menu(run_submenu, back_label="Modules"):
    run_submenu(
        "My Module",
        [
            ("List Items", list_items),
        ],
        back_label=back_label,
    )
    return False
```

Each action callable should return **`False`** when finished (the submenu redisplays). Return a **line count** only if the core admin should show a “press Enter to continue” prompt (same convention as built-in menus).

### `admin_ui` helpers

Import `admin_ui` from `rsmesh_bbs` (same as core `rsmesh-bbs_admin.py`). Module admin code typically uses:

| Function | Purpose |
|----------|---------|
| `paginate_display(page_title, lines, *, empty_message=..., select_prompt=..., select_empty_exits=...)` | Paginated 80×24 list view. Returns `False` on back, or `(line_count, choice)` when `select_prompt` is set and the user enters a value. Navigation: **N** next, **P** prev, **Enter** or **X** back. |
| `display_record_detail(page_title, detail_lines, not_found_message=None)` | Single-record detail screen with “Enter or X=back”. |
| `list_with_record_view(page_title, list_lines_fn, empty_message, view_fn)` | Paginated list with “Enter ID to view”; calls `view_fn(record_id)` for the chosen row. |
| `record_detail_lines(fields)` | Build detail lines from `[("Label", value), ...]`; multiline values are indented. |
| `begin_data_display(page_title)` | Draw the standard SysAdmin header for a data page. |
| `print_page_header(menu_name=None)` | Header line + separator + blank line. |
| `print_bold(message)` | Bold, cropped to display width. |
| `print_separator()` | `=` rule on line 22 layout. |
| `input_bold(prompt)` | Bold prompt, then `input()`. |
| `clear_screen()` | Clear the terminal. |

Layout constants (24-line display): `DISPLAY_COLUMNS`, `CONTENT_START_LINE`, `CONTENT_END_LINE`, `CONTENT_LINES_PER_PAGE`, `MENU_OPTION_INDENT`, and related `HEADER_*` / `MENU_*` line numbers.

`paginate_display` examples:

```python
# Read-only list
admin_ui.paginate_display("List Node Info", lines, empty_message="No nodes in database.")

# Selectable list (returns (lines_on_page, choice) or False)
result = admin_ui.paginate_display(
    "Pick Item",
    lines,
    empty_message="No items.",
    select_prompt="Enter ID or X=back:",
    select_empty_exits=True,
)
if result is not False:
    _, item_id = result
    if item_id.upper() != "X":
        show_item(item_id)
```

For multi-step forms or success messages after add/edit, core admin also uses helpers in `rsmesh-bbs_admin.py` (`begin_form_screen`, `_finish_action_message`, etc.). Module code can import those from the main admin module if needed; list/detail flows should prefer `admin_ui` above.

See `modules/node_info/node_info_admin.py` and `modules/example_hello/example_hello_admin.py` for minimal examples.

## Optional config

`config.yml` in the module directory can hold module-specific settings. Load it from `on_load` using `ctx.path("config.yml")`.

## Examples

- `modules/example_hello/` — minimal module, visit tracking, scheduled greetings via `enqueue_send`
- `modules/fortune/` — random fortunes from `fortunes.txt` (TC²-style `?? fortune ??` decoration)
- `modules/node_info/` — stats menus, bundled node list, sysadmin-only list, background scan/purge schedules

## Testing a new module

1. Create the directory and `module.py`.
2. Enable the module in SysAdmin.
3. Restart the BBS server (modules load at startup).
4. From a mesh handset: main menu → **M[o]dules** (`O`) → your menu option. See [User Guide](RSMESH-BBS-USER-GUIDE.md).
