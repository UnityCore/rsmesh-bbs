# RSMesh BBS

A Meshtastic bulletin board system with mail, channels, peer sync, and an admin tool.

Based on (and sync compatible with) [TC²-BBS-Mesh](https://github.com/TheCommsChannel/TC2-BBS-mesh).

## Requirements

- Python 3.8+ (with `venv` support)
- A Meshtastic node connected by USB serial or TCP (ESP32 WiFi)

## Setup (virtual environment)

Use a project-local virtual environment so dependencies do not mix with system Python packages.

**Linux / macOS**

```bash
cd /path/to/rsmesh-bbs
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
cd C:\path\to\rsmesh-bbs
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

After activation, `python` and `pip` refer to the venv. You can also run scripts without activating by calling the venv interpreter directly (for example `.venv/bin/python` on Linux or `.venv\Scripts\python.exe` on Windows).

## Quick start

1. Complete [Setup (virtual environment)](#setup-virtual-environment) above.
2. Copy `example_config.yml` to `config.yml` and edit for your node.
3. Start the BBS server from the project directory (with the venv activated):

```bash
python rsmesh-bbs_server.py
```

Use `-c` / `--config` to point at a different YAML file, or `-v` / `--version` to print the server version:

```bash
python rsmesh-bbs_server.py -c /path/to/config.yml
python rsmesh-bbs_server.py --version
```

4. Manage the database with the admin tool (no radio required):

```bash
python rsmesh-bbs_admin.py
```

The server creates `rsmesh-bbs.db` in the current working directory. Module data (for example Node Info) is stored under `modules/<name>/`. Run both scripts from the project directory so they use the same files.

## Mesh client (no radio)

`rsmesh-bbs_client.py` simulates a mesh handset in-process — useful for testing menus, mail, and bulletins without a Meshtastic device or running server. It uses the same `rsmesh-bbs.db` and `config.yml` as the server (for board name and other BBS settings), but drives the BBS command handlers directly through a mock interface (no radio, no PyPubSub).

Simulated handset identity (`node_id`, `short_name`) is configured in `config_client.yml`. Copy the starter file before your first run:

```bash
cp example_config_client.yml config_client.yml
```

With the [virtual environment](#setup-virtual-environment) activated:

```bash
python rsmesh-bbs_client.py --fast
```

| Flag | Purpose |
|------|---------|
| `--fast` | Skip mesh reply pacing delays (recommended for interactive use) |
| `-c` / `--config` | Path to `config_client.yml` (default: `./config_client.yml`) |
| `--node-id` | Simulated client node ID (default: from `config_client.yml`) |
| `--node-num` | Simulated client node number (default: derived from node ID) |
| `--short-name` | Simulated client short name (default: from `config_client.yml`) |
| `--long-name` | Simulated client long name (default: `CLI Test User`) |

Example `config_client.yml`:

```yaml
client:
  node_id: "!0c0ffee0"
  short_name: COFY
```

Command-line flags override values from `config_client.yml` when you need a one-off identity. The board banner still comes from `config.yml` in the project directory (see [Configuration reference](#configuration-reference)).

Type messages as you would from a handset (single-letter menu commands such as `B`, `R`, `S`). Press Enter or type `X` for the main menu. Ctrl+C or Ctrl+D to quit.

The pytest `mesh_client` fixture in `tests/conftest.py` uses the same harness against a temporary database. See `tests/test_mesh_client.py` for examples.

## Project layout

```
rsmesh-bbs/
  rsmesh-bbs_server.py    # BBS server entry point
  rsmesh-bbs_admin.py     # Admin tool entry point
  rsmesh-bbs_client.py    # In-process mesh handset simulator (no radio)
  rsmesh_bbs/             # Core library code
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

With the [virtual environment](#setup-virtual-environment) activated, install test dependencies and run the suite from the project directory:

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

## Upgrading from TC²

RSMesh BBS can migrate a stock [TC²-BBS-Mesh](https://github.com/TheCommsChannel/TC2-BBS-mesh) install on first startup. Complete [Setup (virtual environment)](#setup-virtual-environment), place your existing TC² files in the project directory, and start the server with the venv activated:

| TC² file | RSMesh BBS handling |
|----------|---------------------|
| `config.ini` | Converted to `config.yml` if `config.yml` does not already exist |
| `bulletins.db` | Copied to `rsmesh-bbs.db` if `rsmesh-bbs.db` does not already exist |

Migration runs automatically when you start `rsmesh-bbs_server.py`:

1. **`config.ini` → `config.yml`** — `[interface]` type/port/hostname; `bbs.board_name` defaults to **RSMesh BBS**; first `[allow_list]` node as `bbs.superuser_node`
2. **`bulletins.db` → `rsmesh-bbs.db`** — schema upgraded (sync columns, channel `url` → `psk`, new tables)
3. **`[sync] bbs_nodes`** — imported into the `sync_peers` table when that table is empty, with **all sync and ingest flags set to `N`** (sync disabled). The server prints a reminder at startup. Edit each peer in `rsmesh-bbs_admin.py` and enable the sync flags you want before any bulletin, mail, or channel sync runs.
4. **`[allow_list] allowed_nodes`** — imported into `sysadmin_nodes`

Existing `config.yml` or `rsmesh-bbs.db` files are not overwritten. After migration, review `config.yml` (add `schedule` settings if needed) and configure sync peers in `rsmesh-bbs_admin.py` (with the venv activated).

For a new install with no TC² files, complete venv setup and copy `example_config.yml` to `config.yml` instead.

## Cross-platform support

The Python code runs on Linux, Windows, and macOS. Use the same [virtual environment](#setup-virtual-environment) on every platform; differences are mostly about how you connect the radio and how you run the server as a background service.

### Serial (USB) examples

Set `type: serial` and the correct `port` for your OS in `config.yml`:

**Linux**

```yaml
interface:
  type: serial
  port: /dev/ttyUSB0
```

If only one serial device is connected, you can omit `port` and let Meshtastic auto-detect it. On Linux you may need membership in the `dialout` group to access USB serial devices.

**macOS**

```yaml
interface:
  type: serial
  port: /dev/cu.usbmodem101
```

List available ports after plugging in the device:

```bash
ls /dev/cu.*
```

**Windows**

```yaml
interface:
  type: serial
  port: COM3
```

Check Device Manager for the assigned COM port. Use Windows Terminal or another modern console for the admin tool bold formatting.

### TCP (WiFi) example

TCP works the same on all platforms and is useful for ESP32-based nodes:

```yaml
interface:
  type: tcp
  hostname: 192.168.1.100
```

### Running as a service

| Platform | Approach |
|----------|----------|
| **Linux** | Use `rsmesh-bbs.service` as a systemd unit (see below). |
| **macOS** | Run manually with the venv activated, or create a `launchd` plist if you need auto-start. |
| **Windows** | Run manually with the venv activated, or use Task Scheduler to start `.venv\Scripts\python.exe rsmesh-bbs_server.py` at login. |

`rsmesh-bbs_admin.py` is intended for interactive use and does not need to run as a service.

#### Linux systemd

The bundled `rsmesh-bbs.service` expects the project at `/opt/rsmesh-bbs` with dependencies installed in `/opt/rsmesh-bbs/.venv`. Pick an unprivileged Linux account to run the service — a dedicated user is ideal, but an existing login account works too. That account must own the install directory and match `User` / `Group` in the unit file.

The unit file ships with `User=bbs` and `Group=bbs` as placeholders. Either create that account or edit those lines to your chosen username before enabling the service.

```bash
# Optional: create a dedicated system user (skip if using an existing account)
sudo useradd --system --home /opt/rsmesh-bbs --create-home --shell /usr/sbin/nologin bbs

sudo mkdir -p /opt/rsmesh-bbs
sudo git clone git@github.com:UnityCore/rsmesh-bbs.git /opt/rsmesh-bbs
cd /opt/rsmesh-bbs
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp example_config.yml config.yml
# edit config.yml for your node

# Replace bbs with your service account if different
sudo chown -R bbs:bbs /opt/rsmesh-bbs

# Edit User=, Group=, WorkingDirectory=, and ExecStart= if paths or account differ
sudo cp rsmesh-bbs.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rsmesh-bbs
sudo systemctl status rsmesh-bbs
```

After pulling updates, reinstall dependencies when `requirements.txt` changes and ensure the service user still owns the tree (especially if you ran `git pull` as root):

```bash
cd /opt/rsmesh-bbs
git pull
.venv/bin/python -m pip install -r requirements.txt
sudo chown -R bbs:bbs /opt/rsmesh-bbs   # use your service account
sudo systemctl restart rsmesh-bbs
```

If the service fails to start, read the journal for the startup error message:

```bash
sudo journalctl -u rsmesh-bbs -n 50 --no-pager
```

Common causes after enabling the venv-based service:

| Symptom in journal | Fix |
|--------------------|-----|
| `virtual environment not found` | Run `python3 -m venv .venv` and `pip install -r requirements.txt` in `/opt/rsmesh-bbs` |
| `configuration file not found` | Copy and edit `config.yml` in `/opt/rsmesh-bbs` |
| `missing Python package` | `.venv/bin/python -m pip install -r requirements.txt` |
| `cannot write database` / `read-only` / `readonly database` | `sudo chown -R <service-user>:<service-user> /opt/rsmesh-bbs` — the service account must own the database and WAL files |
| `PermissionError` on serial port | Add service user to `dialout` (`SupplementaryGroups=dialout` in the unit file) and verify `interface.port` in `config.yml` |
| `No serial ports detected` | Set `interface.port` explicitly, or use `interface.type: tcp` with `hostname` |

## Configuration reference

| Setting | Location | Notes |
|---------|----------|-------|
| Simulated handset identity | `config_client.yml` `client` | `node_id` and `short_name` for `rsmesh-bbs_client.py` (see `example_config_client.yml`) |
| Board name, superuser, event bus topic | `config.yml` `bbs` | Banner text, Urgent board permission, and PyPubSub receive topic |
| Radio interface | `config.yml` `interface` | `serial` or `tcp`; set `port` or `hostname` as needed |
| Peer sync interval | `config.yml` `schedule` | Minutes between retries for unsynced records |
| Module schedule tick | `config.yml` `schedule` | Minutes between module schedule worker runs (`module_exec_minutes`) |
| Node Info purge / scan | `modules/node_info/config.yml` | Per-module settings (`purge_minutes`, `scan_interval_minutes`) |
| Deleted bulletin purge interval | `config.yml` `schedule` | Minutes between purge runs for bulletins marked deleted (`sync_purge_minutes`) |
| Mesh bulletin display age | `config.yml` `schedule` | Days of non-pinned bulletins shown on mesh boards (`bulletin_display_age_days`) |
| Sync peers | `sync_peers` table | Configure with `rsmesh-bbs_admin.py`. Protocols: `tc2`, `rsv1` (and future `rsv2`, …) |

### Sync wire formats

- **tc2** — pipe-delimited messages (`BULLETIN|`, `MAIL|`, …) for TC²-BBS-mesh compatibility.
- **rsv1** (and later **rsvN**) — `RS|N|TYPE|{json}` only; pipe messages from RS peers are ignored. The digit `N` matches the peer protocol label (`rsv1` → `RS|1|…`). JSON uses compact keys (for example bulletin `b`, `sn`, `sub`, `body`, `uid`). Oversized RS sync payloads are split into `RS|N|CHUNK|{...}` packets and reassembled on ingest. Inbound RS messages accept version fallback when wire and configured versions differ; mismatches surface as **Sync alerts** in the admin tool. **tc2** sync messages must fit in a single 200-byte mesh packet.

| Sysadmin nodes | `sysadmin_nodes` table | Configure with `rsmesh-bbs_admin.py` (also seeded from `superuser_node` and node catalog) |

See `example_config.yml` for a commented starter BBS configuration and `example_config_client.yml` for the mesh client handset identity.

## Channel directory

The BBS maintains a **channel directory**: a list of Meshtastic channel names and PSKs so mesh users can find and join shared channels.

### PSK model

A channel PSK is a **public key for shared channel access**, not a secret credential. The directory exists to distribute PSKs openly — anyone on the mesh can view published entries. The BBS does not validate that a poster controls a PSK or that it matches a live Meshtastic channel; incorrect entries simply fail to attract participants, and posters can submit a corrected entry or contact the operator.

Use **separate PSKs** for private operator traffic that should never appear in the directory.

### Staged publishing

| Source | Default `publish` | Visible on mesh | Synced to peers |
|--------|-------------------|-----------------|-----------------|
| Mesh user **Post** | `N` | No | No |
| Sync peer ingest | `N` | No | No |
| Admin tool **Add Channel** | `Y` | Yes | Yes (when synced) |

Mesh users submit channel name and PSK; the operator reviews unpublished rows in the admin tool and sets **Publish** to `Y` when ready. Only published channels appear in **View** on the mesh or sync outbound to peers.

### Sync peer trust

Configure sync peers in the admin tool. **Ingest channels in** controls whether a peer may add channel rows to your database (always unpublished until you approve). **Sync channels out** controls whether your published channels are sent to that peer. Limit ingest on untrusted peers.

## Admin tool

Run `rsmesh-bbs_admin.py` from the project directory with the [virtual environment](#setup-virtual-environment) activated (same as the server). It manages bulletins, mail, channels, the node catalog, sync peers, modules, and bulletin delete reconciliation. Module-specific admin screens live in `modules/<name>/<name>_admin.py` and are linked from **Administration → Modules**. Shared display helpers (page headers, pagination, record detail views) are in `admin_ui.py` for use by core and module admin code.

Sync peer and sysadmin changes made in the admin tool are picked up by the running server automatically (on the next mesh message or background worker cycle).

**Administration → Backup** creates a timestamped `backup/backup_YYYYMMDDHHMMSS.zip`. SQL dumps are written briefly under `backup/staging/` (same layout as the live tree), then removed after the zip is created. The archive contains those SQL dumps (for example `rsmesh-bbs.sql`, `modules/node_info/node_info.sql`) plus `config.yml` files. Dumps use SQLite’s connection API, so WAL sidecar files are not required. Restore by unzipping and loading each `.sql` with `sqlite3 database.db < dump.sql`.

## Modules

Mesh modules extend the BBS without modifying core code. Each module lives in `modules/<name>/`:

| File | Purpose |
|------|---------|
| `module.py` | Mesh menu handler (`on_load`, `handle_menu`, scheduled tasks) |
| `<name>_admin.py` | Optional admin submenu (`run_admin_menu(run_submenu, back_label)`) |
| `config.yml` | Module-specific settings |

Modules are registered in the `modules` table (seeded at startup). Users reach enabled modules from the mesh main menu via **[M]odules**. Admins manage modules under **Administration → Modules** (list, enable/disable flags, and per-module admin screens when `<name>_admin.py` exists).

Module admin code should use `rsmesh_bbs.admin_ui` for consistent headers, pagination (`paginate_display`), and record detail views (`display_record_detail`, `list_with_record_view`).

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

## Thanks to

- [TC²-BBS](https://github.com/TheCommsChannel/TC2-BBS-mesh)
- [Meshtastic](https://github.com/meshtastic)

## License

GPL-3.0-only. See [LICENSE](LICENSE).
