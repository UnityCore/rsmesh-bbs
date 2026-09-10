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

Simulated handset identity (`node_id`, `short_name`, `long_name`) is configured in `config_client.yml`. Copy the starter file before your first run:

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
| `--long-name` | Simulated client long name (default: from `config_client.yml`) |

Example `config_client.yml`:

```yaml
client:
  node_id: "!0c0ffee0"
  short_name: COFY
  long_name: CLI Test User
```

Command-line flags override values from `config_client.yml` when you need a one-off identity. The board banner still comes from `config.yml` in the project directory (see [Configuration reference](#configuration-reference)).

Type messages as you would from a handset (single-letter menu commands such as `B`, `R`, `S`). Press Enter or type `X` for the main menu. Ctrl+C or Ctrl+D to quit.

The pytest `mesh_client` fixture in `tests/conftest.py` uses the same harness against a temporary database. See `tests/test_mesh_client.py` for examples.

## Using the BBS from the mesh

Send commands as **direct messages to the BBS node**. The server ignores group-channel traffic and messages addressed to other nodes. After connecting, send any letter command or an unrecognized message to open the main menu.

### Main menu

```
[B]ulletins  [C]hannels
[R]ead Mail  [S]end Mail
[M]odules    E[X]IT
```

| Key | Action |
|-----|--------|
| `B` | Bulletin boards |
| `C` | Channel directory (view published channels or post a new entry) |
| `R` | Read mail |
| `S` | Send mail |
| `M` | Enabled modules (Fortune, Node Info, etc.) |
| `X` | Main menu (also `E[X]IT` prompts in submenus) |

Many submenus accept a two-letter exit shortcut (for example `Rx` runs **R** then returns to the main menu via **X**).

### Bulletins

Board menu: `[G]eneral` `[I]nfo` `[N]ews` `[U]rgent`

On a board: `[R]ead` `[P]ost`, and `[D]elete` for **sysadmin** nodes only. **Urgent** posting is also sysadmin-only.

- **Read** — pick a bulletin number from the list, then `X` to return to the board menu.
- **Post** — enter a short subject, then send the body across one or more messages; send `END` on its own line to finish.
- **Delete** (sysadmin) — pick a bulletin number to soft-delete.

See [Pinned bulletins](#pinned-bulletins) and [Urgent board alerts](#urgent-board-alerts) for operator-controlled behavior.

### Mail

**Read mail** — select a message number, then `[K]eep`, `[D]elete`, or `[R]eply`. Reply uses the same multiline `END` flow as posting.

**Send mail** — enter the recipient **short name** (or pick from a list when several nodes match). Subject, then body with `END` to finish. Recipient lookup uses nodes seen on the radio, the [mesh node directory](#node-directory), the [node catalog](#node-catalog-operator-reference), and the Node Info module when enabled.

### Channel directory

`[V]iew` — list published channels and show name/PSK for a selected entry.

`[P]ost` — submit a channel name and PSK for operator review. Mesh posts are stored unpublished until an operator sets **Publish** to `Y` in the admin tool (see [Channel directory](#channel-directory)).

### Sysadmin capabilities on the mesh

Sysadmin nodes (`sysadmin_nodes`, seeded from `bbs.superuser_node` and node catalog **BBS Admin**) can post to **Urgent**, delete bulletins on any board, and use extra module actions where documented (for example Node Info **List Nodes**).

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
| Simulated handset identity | `config_client.yml` `client` | `node_id`, `short_name`, and `long_name` for `rsmesh-bbs_client.py` (see `example_config_client.yml`) |
| Board name, superuser, event bus topic | `config.yml` `bbs` | Banner text, Urgent board permission, and PyPubSub topic for incoming radio packets (`eventbus_topic`, default `meshtastic.receive`) |
| Urgent mesh alerts (local) | `config.yml` `bbs` `send_urgent_alert_local` | `true`/`false` — broadcast on primary channel when an Urgent bulletin is posted on this node (default `false`) |
| Urgent mesh alerts (sync) | `config.yml` `bbs` `send_urgent_alert_from_sync` | `true`/`false` — broadcast when an Urgent bulletin is ingested from a sync peer (default `false`) |
| Radio interface | `config.yml` `interface` | `serial` or `tcp`; set `port` or `hostname` as needed |
| Peer sync interval | `config.yml` `schedule` | Minutes between retries for unsynced records |
| Module schedule tick | `config.yml` `schedule` | Minutes between module schedule worker runs (`module_exec_minutes`) |
| Node Info purge / scan | `modules/node_info/config.yml` | Per-module settings (`purge_minutes`, `scan_interval_minutes`) |
| Deleted bulletin purge interval | `config.yml` `schedule` | Minutes between purge runs for bulletins marked deleted (`sync_purge_minutes`) |
| Mesh bulletin display age | `config.yml` `schedule` | Days of non-pinned bulletins shown on mesh boards (`bulletin_display_age_days`) |
| Sync peers | `sync_peers` table | Configure with `rsmesh-bbs_admin.py`. Protocols: `tc2`, `rsv1` (and future `rsv2`, …) |

### Sync wire formats

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

**rsv1** (and later **rsvN**) uses compact JSON keys (for example bulletin `b`, `sn`, `sub`, `body`, `uid`, `pin`). The digit `N` matches the peer protocol label (`rsv1` → `RS|1|…`). Inbound RS messages accept version fallback when wire and configured versions differ; mismatches surface as **Sync alerts** in the admin tool.

| Sysadmin nodes | `sysadmin_nodes` table | Configure with `rsmesh-bbs_admin.py` (also seeded from `superuser_node` and node catalog) |

See `example_config.yml` for a commented starter BBS configuration and `example_config_client.yml` for the mesh client handset identity.

### Urgent board alerts

The **Urgent** bulletin board is restricted to sysadmin nodes for posting. When enabled, new Urgent bulletins can trigger a mesh-wide broadcast on the radio primary channel (channel index 0).

| Setting | Default | Behavior |
|---------|---------|----------|
| `send_urgent_alert_local` | `false` | Broadcast when a user posts Urgent on this BBS, or when an operator adds an Urgent bulletin in the admin tool |
| `send_urgent_alert_from_sync` | `false` | Broadcast when an Urgent bulletin arrives from a sync peer |

Both settings use `true` or `false`. Changes take effect immediately via `sys_config` (admin tool or server restart seeding from `config.yml`).

**Local posts** from mesh users are sent immediately when `send_urgent_alert_local` is `true`. **Admin Add Bulletin** queues the alert in the database; the running server delivers it on the main loop (typically within about one second). Editing a bulletin does not queue or send an alert.

If `send_urgent_alert_local` is turned off while alerts are queued, the server drops queued rows without sending. Queued alerts are only created when the setting is `true` at add time.

Before sending a queued alert, the server verifies the bulletin still exists and is still on the Urgent board.

### Pinned bulletins

Operators can pin important bulletins so they stay visible on mesh boards longer than normal posts. Pinning is set in the admin tool (**Bulletins → Edit Bulletin → Pinned Y/N**). Mesh users cannot pin or unpin from the handset.

| Audience | What they see |
|----------|----------------|
| **Mesh users** | Pinned bulletins (`pinned = Y`) always appear in board lists and can be read, regardless of age. Non-pinned bulletins drop off after `schedule.bulletin_display_age_days` (default 30 days). Pinned entries are listed first on each board. |
| **Admin tool** | All non-deleted bulletins, including older unpinned posts, for full management. |

New bulletins are unpinned by default. Changing the pinned flag (or other bulletin fields) in **Edit Bulletin** marks the record unsynced so the update can sync to **rsv1** peers. **tc2** peers receive only the original bulletin create and do not get pin or edit updates.

## Mail forwarding

When mail is delivered to a recipient that matches a **node catalog** entry (by hex node ID or short name), the server checks **BBS Mail Forward To**. If set, the message is stored for the resolved forward target instead, and a footer line is appended: `Sent to {original short name}`.

The forward target can be a catalog hex ID or short name, or resolved through the same short-name lookup used for send mail. If the target cannot be resolved, mail stays with the original recipient. Forwarding does not apply to mail that only matches `mesh_nodes` or live radio nodes without a catalog row.

Configure forwarding under **Administration → Node Catalog** in the admin tool. See [Node catalog (operator reference)](#node-catalog-operator-reference).

## Node directory

Three related stores serve different purposes:

| Store | Where | Purpose |
|-------|--------|---------|
| **Node catalog** | Main DB (`node_catalog`) | Operator-maintained reference (optional notes, mail forward, BBS admin flags) |
| **Mesh nodes** | Main DB (`mesh_nodes`) | Core minimal node directory (hex ID, short/long name, last heard) for server operations |
| **Node Info** | `modules/node_info/node_info.db` | Optional module — enhanced telemetry reference (signal, GPS, hops, etc.) |

### Short-name and hex ID resolution

When a mesh user sends mail (or sync normalizes a node reference), the server resolves short names against, in order:

1. Nodes currently known to the attached radio (`interface.nodes`)
2. **Mesh nodes** table
3. **Node Info** module directory (when enabled)
4. **Node catalog** (when a matching short name exists)

Any of these can supply a hex node ID for delivery. The catalog is one helper among several — you do not need catalog rows for nodes the radio already knows.

### Mesh nodes vs Node Info

**Mesh nodes** is part of the core database and is always available. The server maintains it automatically from live mesh traffic (any packet the radio hears) and, when configured, from **rsv1** peer **Sync mesh nodes** ingest. Each row stores only what the BBS needs for day-to-day operation: hex node ID, short name, long name, and last heard. That minimal record supports mail recipient lookup, short-name resolution when the radio’s live node list is incomplete, and mesh-node sync between peers — **even when the Node Info module is disabled**.

**Node Info** is an **optional module** (enabled by default, but you can turn it off under **Administration → Modules**). It keeps a separate, richer telemetry database: SNR, RSSI, hop count, GPS coordinates, channel-quality estimates, and related fields gathered from overheard packets. Mesh users reach it from **[M]odules** for node counts and statistics; sysadmins can list detailed rows. Think of Node Info as an **enhanced telemetry reference**, not a requirement for core BBS features.

If Node Info is off, mail, sync, and short-name resolution still work through the attached radio’s live node list, the **mesh nodes** table, and the optional **node catalog**.

### Node catalog (operator reference)

The **node catalog** is a **convenience for the system operator**: an optional notebook of nodes you care about. It is not required for normal BBS operation.

**What the server uses at runtime:**

| Field | Used by server? |
|-------|-----------------|
| `short_name`, `node_hex_username`, `long_name` | Yes — short-name/hex lookup and mail inbox matching |
| `bbs_mail_forward_to` | Yes — [mail forwarding](#mail-forwarding) |
| `bbs_admin` | Yes — when `Y`, syncs `sysadmin_nodes` (Urgent post, bulletin delete on mesh) |
| `mesh_admin` | No — operator reference only (see below) |
| `public_key`, `private_key`, `ble_pin`, `has_gps`, `hardware`, `comment` | No — optional operator notes; safe to leave blank (defaults apply for BLE PIN) |

You may store keys and PINs for your own reference, but the BBS never uses them for mesh or sync behavior.

**Mesh Admin** (`mesh_admin`) is an operator notebook flag: it marks that **this catalog node is intended to perform remote administration on other nodes** — not that other nodes can administer it. A node with `mesh_admin = Y` is your administrator handset or gateway: its public key is the one you add on **other** radios under **Radio Config → Security → Admin Settings** (Primary, Secondary, or Tertiary Admin Key). Those target nodes will then accept configuration changes from the Mesh Admin node to the extent Meshtastic allows. The catalog field only records that you have set up (or plan to set up) that relationship; the BBS does **not** read `mesh_admin` and **cannot** push config to any radio that has not been configured to accept it. Use the catalog **Public key** field optionally to store the Mesh Admin node's key for your own fleet documentation.

**Mesh nodes** — see [Mesh nodes vs Node Info](#mesh-nodes-vs-node-info). Operators can also add, edit, import, or purge rows in the admin tool (**Administration → Mesh Nodes**).

**Node Info** — optional enhanced telemetry module; configure purge/scan in `modules/node_info/config.yml`. See [Shipped modules (mesh menus)](#shipped-modules-mesh-menus).

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

## Operator concepts

Background workers in the running server (intervals from `config.yml` `schedule`):

| Worker | Setting | Behavior |
|--------|---------|----------|
| Peer sync | `peer_sync_minutes` | Retries unsynced bulletins, mail, and published channels to eligible sync peers |
| Purge | `sync_purge_minutes` | Reloads peer/sysadmin config; purges soft-deleted bulletins/channels and pushes delete sync |
| Module schedule | `module_exec_minutes` | Runs enabled module scheduled tasks (Node Info scan/purge, etc.) |

**Soft delete** — Admin **Delete Bulletins** / **Delete Channels** (and mesh sysadmin bulletin delete) set `deleted='Y'`. The purge worker removes them locally and syncs deletes to peers. **List Unsynced Data** in the admin tool shows records still pending peer sync.

**Reconcile** — When a sync peer deletes a bulletin or channel, your copy is marked `delete_reconcile='Y'` until an operator restores or permanently deletes it (**Review Reconcile** menus).

**Sysconfig** — Many `config.yml` values are copied into the `sys_config` table on first run. The admin tool can edit them live; **Export Configuration to config.yml** writes the database values back to `config.yml`.

## Admin tool

Run `rsmesh-bbs_admin.py` from the project directory with the [virtual environment](#setup-virtual-environment) activated (same as the server). It manages bulletins, mail, channels, the node catalog, sync peers, modules, and bulletin delete reconciliation. Module-specific admin screens live in `modules/<name>/<name>_admin.py` and are linked from **Administration → Modules**. Shared display helpers (page headers, pagination, record detail views) are in `admin_ui.py` for use by core and module admin code.

See [README-ADMIN.md](README-ADMIN.md) for a complete guide to every admin menu, input prompt, and valid choice.

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

### Shipped modules (mesh menus)

Enable under **Administration → Modules**. Users open them from **[M]odules** on the main menu.

| Module | Menu option | Mesh actions |
|--------|-------------|--------------|
| **Fortune** | `F` (default) | Shows a random fortune on entry; any message fetches another; `X` exits |
| **Node Info** | (per `modules` table) | `[N]odes` counts by time window, `[H]ardware` model counts, `[R]oles` role counts; sysadmins also get `[L]ist Nodes` (detailed signal/GPS lines) |
| **Example Hello** | (disabled by default) | Greets on entry; demonstrates visits DB and scheduled greetings |

Fortune has no admin screen. Node Info admin is view-only (**List Node Info**). See [modules/README.md](modules/README.md) for module development.

## Thanks to

- [TC²-BBS](https://github.com/TheCommsChannel/TC2-BBS-mesh)
- [Meshtastic](https://github.com/meshtastic)

## License

GPL-3.0-only. See [LICENSE](LICENSE).
