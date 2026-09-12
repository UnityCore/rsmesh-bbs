# RSMesh BBS Developer Guide

Release 1.1

Reference for contributors and module authors: repository layout, tests, the module framework, and peer sync wire formats.

## Table of contents

- [Project layout](#project-layout)
- [Tests](#tests)
- [Modules](#modules)
  - [Directory layout](#directory-layout)
  - [Module class](#module-class)
  - [ModuleContext (`ctx`)](#modulecontext-ctx)
    - [Sending mesh messages safely](#sending-mesh-messages-safely)
    - [Ordering content and menus](#ordering-content-and-menus)
  - [Scheduled tasks](#scheduled-tasks)
  - [Optional admin UI](#optional-admin-ui)
    - [Admin module contract](#admin-module-contract)
    - [`admin_ui` helpers](#admin_ui-helpers)
  - [Optional config](#optional-config)
  - [Example module (`example_hello`)](#example-module-example_hello)
  - [Reference modules](#reference-modules)
  - [Testing a new module](#testing-a-new-module)
- [Sync wire formats](#sync-wire-formats)
  - [rsv1 sync message examples](#rsv1-sync-message-examples)
    - [Envelope](#envelope)
    - [BULLETIN](#bulletin)
    - [MAIL](#mail)
    - [CHANNEL](#channel)
    - [DELETE_BULLETIN](#delete_bulletin)
    - [DELETE_MAIL](#delete_mail)
    - [DELETE_CHANNEL](#delete_channel)
    - [NODE](#node)
    - [CHUNK (transport wrapper)](#chunk-transport-wrapper)
    - [Quick reference](#quick-reference)

## Project layout

```
rsmesh-bbs/
  rsmesh-bbs_server.py    # BBS server entry point
  rsmesh-bbs_admin.py     # Admin tool entry point
  rsmesh-bbs_client.py    # In-process mesh handset simulator (no radio)
  rsmesh_bbs/             # Core library code
  mesh_ui/                # Cached mesh main menu body (main_menu.txt)
  modules/                # Optional mesh modules
  tests/                  # Automated tests (pytest)
  .venv/                  # Virtual environment (created locally; not in git)
  config.yml              # Runtime BBS configuration (not in git)
  config_client.yml       # Simulated handset identity for the mesh client (not in git)
  backup/                 # SQL backup archives
  example_config.yml
  example_config_client.yml
  requirements.txt
  requirements-dev.txt    # Test dependencies (pytest)
```

Launcher scripts stay at the project root; supporting Python modules live in `rsmesh_bbs/` (including `mesh_client.py` and `mock_interface.py` for the CLI client).

## Tests

Automated tests cover RS sync wire encode/decode, oversized payload chunking, delete/ingest idempotency, and in-process mesh client flows (menus and mail). Database tests use a temporary SQLite file under pytest's `tmp_path`; they do not read or write your live `rsmesh-bbs.db`.

With the [virtual environment](../README.md#setup-virtual-environment) activated, install test dependencies and run the suite from the project directory:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Useful variants:

```bash
python -m pytest -v
python -m pytest tests/test_sync_wire.py
python -m pytest tests/test_mesh_client.py
python -m pytest -k chunk
```

Run tests before committing changes to sync or delete behavior, or anytime you want a quick regression check.

## Modules

Mesh modules extend the BBS without modifying core code. Each module lives in its own subdirectory under `modules/`.

### Directory layout

```
modules/
  my_module/
    module.py          # Required: Module class
    config.yml         # Optional: module settings
    my_module_admin.py # Optional: SysAdmin UI hooks
    storage.py         # Optional: data/helpers
```

| File | Purpose |
|------|---------|
| `module.py` | Mesh menu handler (`on_load`, `handle_menu`, scheduled tasks) |
| `<name>_admin.py` | Optional admin submenu (`run_admin_menu(run_submenu, back_label)`) |
| `config.yml` | Module-specific settings |

Modules are registered in the `modules` table (seeded at startup). Enable modules in the SysAdmin **Modules** menu. Mesh users open the module list from the main menu with **M[o]dules** (`O`). Each enabled module appears there using its configured menu option letter. When a core service is disabled, its main-menu key (`B`, `C`, or `M`) can be claimed by a module instead.

Shipped modules available to mesh users are listed in the [Sysop Guide](RSMESH-BBS-SYSOP-GUIDE.md#shipped-modules-mesh-menus).

### Module class

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

### ModuleContext (`ctx`)

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
| `ctx.register_sync(registration)` | Register optional peer sync handlers (`ModuleSyncRegistration`). |

#### Sending mesh messages safely

Mesh sends must run on the **pubsub receive thread**. Calling `ctx.send*` from `on_enter` or `on_message` is safe because those run on that thread.

**Scheduled tasks** (`register_schedule`) run on a background worker thread. Do **not** call `ctx.send` or `ctx.send_user_message` from a schedule callback — use `ctx.enqueue_send` or `ctx.enqueue_send_messages` instead. The server drains the queue on incoming packets and once per second in its main loop.

#### Ordering content and menus

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

### Scheduled tasks

```python
def on_load(self, ctx):
    ctx.register_schedule("hourly_task", 60, self._hourly)

def _hourly(self, ctx):
    for sender_id in storage.pending_notify():
        ctx.enqueue_send(sender_id, "Scheduled hello!")
```

Interval is in **minutes**. Tasks run only while the module is enabled and schedule is enabled in SysAdmin.

### Peer sync (Phase A, rsv1 only)

Enabled modules may register optional sync participation from `on_load`. Module sync uses the **rsv1** RS wire envelope (`RS|1|TYPE|{json}`) only; the fixed **tc2** pipe format is for core Bulletins, Mail, and Channels and does not support custom module types. Modules use their own `record_type` string (for example `module:events`) in the shared `record_sync_peers` table.

```python
from rsmesh_bbs.module_loader import MODULE_RESULT_CONTINUE, MODULE_RESULT_EXIT
from rsmesh_bbs.module_sync import (
    ModuleSyncRegistration,
    get_pending_sync_peers,
    mark_sync_peers_synced,
    reset_record_sync_peers,
)
from rsmesh_bbs.sync_wire import build_rs_message
from rsmesh_bbs.utils import send_sync_message, sync_peer_bbs_node, sync_peer_protocol


class Module:
    def on_load(self, ctx):
        ctx.register_sync(ModuleSyncRegistration(
            module_id=ctx.id,
            record_type="module:events",
            wire_types=("EVENT",),
            on_inbound_rs=self._ingest_event_rs,
            sync_pending=self._sync_pending_events,
        ))

    def _ingest_event_rs(self, msg_type, fields, sender_node_id, interface):
        # fields is the RS JSON object from the wire envelope
        ...

    def _sync_pending_events(self, peers, interface):
        for record_key, data in storage.pending_for_sync():
            pending = get_pending_sync_peers("module:events", record_key, peers)
            if not pending:
                continue
            synced = []
            for peer in pending:
                message = build_rs_message(1, "EVENT", data)
                if send_sync_message(
                    message,
                    sync_peer_bbs_node(peer),
                    interface,
                    sync_peer_protocol(peer),
                ):
                    synced.append(peer)
            mark_sync_peers_synced("module:events", record_key, synced)
```

| Registration field | Purpose |
|--------------------|---------|
| `record_type` | Namespace for `record_sync_peers` rows (use a `module:` prefix) |
| `wire_types` | RS envelope types owned by this module (`RS\|1\|TYPE\|{json}`) |
| `on_inbound_rs` | Called for RS wire messages when the module is enabled |
| `sync_pending` | Called from the background sync worker with all enabled peers |
| `list_unsynced` | Optional callback returning `(record_key, label)` pairs for admin **List Unsynced Data** |
| `sync_status_lines` | Optional callback receiving `ModuleSyncStatus`; return custom lines for **Administration → Modules → Module Sync Status** |

**Gating:** inbound and outbound module sync are skipped when the module is disabled in SysAdmin. Per-peer module flags are configured under **Administration → Sync Peers** (rsv1 only).

**Helpers** in `rsmesh_bbs.module_sync`: `get_pending_sync_peers`, `mark_sync_peers_synced`, `reset_record_sync_peers`, `decode_module_rs_payload`, `get_module_unsynced_records`, `get_module_sync_status`, `get_module_sync_status_lines`, `count_module_sync_alert_peers`.

**List Unsynced:** implement `list_unsynced` to return keys the module still needs to push. The admin tool shows only records with pending peers according to `record_sync_peers` and peer eligibility.

**Module sync status:** `get_module_sync_status(module_id)` returns a `ModuleSyncStatus` dataclass (pending records, pending peers, per-peer flags). Use it from `{module_dir}_admin.py` to build a module-specific detail screen, or supply `sync_status_lines` on the registration for the core **Module Sync Status** view. The admin splash and **System Status** line shows `Sync alerts: RS version: N peers, Modules: N peers` where the module count is the number of distinct peers with pending module-owned records.

Store module-owned data in the module directory (for example `ctx.path("events.db")`). Track pending sync with `record_sync_peers` and call `reset_record_sync_peers` when a local record changes.

### Optional admin UI

Module-specific admin screens live in `modules/<name>/<name>_admin.py` and are linked from **Administration → Modules** in the admin tool when the module is enabled and the file exists. Add `{module_dir}_admin.py` beside `module.py` (for example `modules/node_info/node_info_admin.py`).

Shared display helpers for core and module admin code (page headers, pagination, record detail views) are in `rsmesh_bbs/admin_ui.py`. Module admin code should use `rsmesh_bbs.admin_ui` rather than reimplementing list and detail layouts.

#### Admin module contract

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

#### `admin_ui` helpers

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

### Optional config

`config.yml` in the module directory can hold module-specific settings. Load it from `on_load` using `ctx.path("config.yml")`.

### Example module (`example_hello`)

A reference implementation (disabled by default) lives in `modules/example_hello/`. Enable it under **Administration → Modules** and set **Schedule enabled** to `Y` for scheduled tasks to run. It demonstrates:

| Pattern | How |
|---------|-----|
| `on_load` / `on_enter` / `on_message` | Records a visit on entry; exits on `X` |
| Module `config.yml` | `schedule_minutes`, `max_visits` |
| Module-local SQLite DB | `visits` table with `short_name`, `visited_at`, `greet_pending` |
| `register_schedule` | Sends `Hello {short_name}!` on the next tick, then trims to the last 5 visits |
| `example_hello_admin.py` | Lists visit history from the admin tool |

Not shown in the example (see `node_info` for these): `register_service` for other core/module code, `send_bundled` for long mesh output, `ctx.is_sysadmin()` permission checks, and mesh-side scanning of `interface.nodes`.

### Reference modules

- `modules/example_hello/` — minimal module, visit tracking, scheduled greetings via `enqueue_send`
- `modules/fortune/` — random fortunes from `fortunes.txt` (TC²-style `?? fortune ??` decoration)
- `modules/bbs_list/` — synced directory of mesh BBS boards (Phase C reference module using `register_sync`)
- `modules/node_info/` — stats menus, bundled node list, sysadmin-only list, background scan/purge schedules

### Testing a new module

1. Create the directory and `module.py`.
2. Enable the module in SysAdmin.
3. Restart the BBS server (modules load at startup).
4. From a mesh handset: main menu → **M[o]dules** (`O`) → your menu option. See the [User Guide](RSMESH-BBS-USER-GUIDE.md).

## Sync wire formats

RSMesh BBS supports two peer sync protocol families. Choose the protocol per sync peer in the admin tool. **tc2** preserves wire compatibility with [TC²-BBS-mesh](https://github.com/TheCommsChannel/TC2-BBS-mesh); **rsv1** is the RSMesh extended format for operators running RSMesh (or other RS-aware) peers.

| Topic | **tc2** | **rsv1** |
|-------|---------|----------|
| On-wire shape | Pipe-delimited (`BULLETIN\|`, `MAIL\|`, …) | `RS\|N\|TYPE\|{json}` only; pipe messages from RS peers are ignored |
| TC² compatibility | Yes — follows TC²-BBS-mesh sync conventions | No — RS peers must also use rsv1 |
| Packet size | Single mesh packet (200 bytes max) | Chunked `RS\|N\|CHUNK\|{...}` reassembly for oversized payloads |
| Bulletin ingest | Insert-only by `unique_id` (duplicate ingests skipped) | Upsert by `unique_id` (edits and pin changes propagate) |
| Pinned bulletins | Not on the wire; pin state is local to each node | `pin` field (`Y`/`N`) in bulletin JSON |
| Mesh node sync | Not supported | `NODE` messages when **Sync mesh nodes** is enabled |
| Channel delete sync | Reconcile workflow | `DELETE_CHANNEL` by `unique_id` |

**tc2** behavior intentionally tracks TC² standards: bulletin sync is create-only, and features such as pinned posts or bulletin edits after the initial sync are not replicated to tc2 peers.

**rsv1** (and later **rsvN**) uses compact JSON keys (for example bulletin `b`, `sn`, `sub`, `body`, `uid`, `pin`). The digit `N` matches the peer protocol label (`rsv1` → `RS|1|…`). Inbound RS messages accept version fallback when wire and configured versions differ; mismatches surface as **Sync alerts** in the admin tool. See [rsv1 sync message examples](#rsv1-sync-message-examples) below. Peer sync flags are configured in the [Sysop Guide](RSMESH-BBS-SYSOP-GUIDE.md#sync-peers).

### rsv1 sync message examples

Examples of every **rsv1** peer sync message on the mesh wire. These samples were generated from the encode functions in `rsmesh_bbs/sync_wire.py`. On the wire, JSON is compact (no spaces); pretty JSON is shown below for readability.

#### Envelope

Every rsv1 message uses:

```
RS|1|<TYPE>|<json-payload>
```

| Part | Meaning |
|------|---------|
| `RS` | Wire prefix |
| `1` | Wire version (`rsv1` → `RS|1|…`) |
| `<TYPE>` | Message type (uppercase) |
| `<json-payload>` | Compact JSON object |

#### BULLETIN

**Keys:** `b` board, `sn` sender short name, `sub` subject, `body` content, `uid` unique ID, `pin` pinned (`Y`/`N`)

**Unpinned (create or update):**

```
RS|1|BULLETIN|{"b":"General","sn":"OPS","sub":"Trail conditions","body":"Muddy north of mile 3.","uid":"550e8400-e29b-41d4-a716-446655440001","pin":"N"}
```

```json
{
  "b": "General",
  "sn": "OPS",
  "sub": "Trail conditions",
  "body": "Muddy north of mile 3.",
  "uid": "550e8400-e29b-41d4-a716-446655440001",
  "pin": "N"
}
```

**Pinned urgent bulletin:**

```
RS|1|BULLETIN|{"b":"Urgent","sn":"OPS","sub":"Evacuation notice","body":"Leave sector 4 immediately.","uid":"550e8400-e29b-41d4-a716-446655440001","pin":"Y"}
```

**Notes:** Upsert by `uid` on ingest. Missing `pin` decodes as `N`. Re-sending with the same `uid` updates board, subject, body, and pin on rsv1 peers.

#### MAIL

**Keys:** `s` sender hex ID, `ssn` sender short name, `r` recipient hex ID, `rsn` recipient short name, `sub`, `body`, `uid`

**Hex recipient:**

```
RS|1|MAIL|{"s":"!a1b2c3d4","ssn":"ALICE","r":"!e5f6a7b8","rsn":"BOB","sub":"Meet at base","body":"Radio check at 1800.","uid":"550e8400-e29b-41d4-a716-446655440002"}
```

```json
{
  "s": "!a1b2c3d4",
  "ssn": "ALICE",
  "r": "!e5f6a7b8",
  "rsn": "BOB",
  "sub": "Meet at base",
  "body": "Radio check at 1800.",
  "uid": "550e8400-e29b-41d4-a716-446655440002"
}
```

**Short-name recipient** (`r` empty, `rsn` used):

```
RS|1|MAIL|{"s":"!a1b2c3d4","ssn":"ALICE","r":"","rsn":"BOB","sub":"Ping","body":"Are you up?","uid":"550e8400-e29b-41d4-a716-446655440002"}
```

**Notes:** Insert-only by `uid` (duplicate ingests skipped).

#### CHANNEL

**Keys:** `n` name, `psk` PSK, `uid` unique ID

```
RS|1|CHANNEL|{"n":"mesh-chat","psk":"AQ==","uid":"550e8400-e29b-41d4-a716-446655440003"}
```

```json
{
  "n": "mesh-chat",
  "psk": "AQ==",
  "uid": "550e8400-e29b-41d4-a716-446655440003"
}
```

**Notes:** `uid` is required for rsv1. Ingested channels are unpublished locally.

#### DELETE_BULLETIN

**Keys:** `uid` bulletin unique ID

```
RS|1|DELETE_BULLETIN|{"uid":"550e8400-e29b-41d4-a716-446655440001"}
```

```json
{ "uid": "550e8400-e29b-41d4-a716-446655440001" }
```

**Notes:** On rsv1 peers, deletes by `uid` directly (no tc2-style reconcile workflow).

#### DELETE_MAIL

**Keys:** `uid` mail unique ID

```
RS|1|DELETE_MAIL|{"uid":"550e8400-e29b-41d4-a716-446655440002"}
```

```json
{ "uid": "550e8400-e29b-41d4-a716-446655440002" }
```

#### DELETE_CHANNEL

**Keys:** `uid` channel unique ID

```
RS|1|DELETE_CHANNEL|{"uid":"550e8400-e29b-41d4-a716-446655440003"}
```

```json
{ "uid": "550e8400-e29b-41d4-a716-446655440003" }
```

**Notes:** rsv1-only; triggers reconcile workflow on the receiving peer.

#### NODE

**Keys:** `id` node hex ID, `sn` short name, `ln` long name, `lh` last heard (Unix epoch string)

```
RS|1|NODE|{"id":"!a1b2c3d4","sn":"ALICE","ln":"Alice Node","lh":"1700000000"}
```

```json
{
  "id": "!a1b2c3d4",
  "sn": "ALICE",
  "ln": "Alice Node",
  "lh": "1700000000"
}
```

**Notes:** rsv1-only. Used when **Sync mesh nodes** is enabled on the peer.

#### CHUNK (transport wrapper)

When a complete `RS|1|…` message exceeds **200 bytes**, it is split into one or more `CHUNK` packets. Each chunk carries a fragment of the **inner** message string.

**Keys:** `u` transfer UUID, `i` chunk index (0-based), `n` total chunks, `p` payload fragment

**Example (chunk 0 of 4 for an oversized BULLETIN):**

```
RS|1|CHUNK|{"u":"95f49967-6bc2-4e9c-b970-0eb671154b02","i":0,"n":4,"p":"RS|1|BULLETIN|{\"b\":\"General\",\"sn\":\"OPS\",\"sub\":\"Large post\",\"body\":\"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
```

```json
{
  "u": "95f49967-6bc2-4e9c-b970-0eb671154b02",
  "i": 0,
  "n": 4,
  "p": "RS|1|BULLETIN|{\"b\":\"General\",\"sn\":\"OPS\",\"sub\":\"Large post\",\"body\":\"xxxxxxxx..."
}
```

**Notes:** Reassembly concatenates all `p` fragments in order (`i` 0 … `n-1`) to rebuild the inner message, which is then parsed as a normal `RS|1|TYPE|…` envelope. Partial sequences expire after 300 seconds.

#### Quick reference

| Type | JSON keys | rsv1-only? |
|------|-----------|------------|
| `BULLETIN` | `b`, `sn`, `sub`, `body`, `uid`, `pin` | No (tc2 uses pipe format) |
| `MAIL` | `s`, `ssn`, `r`, `rsn`, `sub`, `body`, `uid` | No |
| `CHANNEL` | `n`, `psk`, `uid` | No (`uid` required on rsv1) |
| `DELETE_BULLETIN` | `uid` | No |
| `DELETE_MAIL` | `uid` | No |
| `DELETE_CHANNEL` | `uid` | Yes |
| `NODE` | `id`, `sn`, `ln`, `lh` | Yes |
| `CHUNK` | `u`, `i`, `n`, `p` | Yes (transport) |
