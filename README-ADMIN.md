# RSMesh BBS Admin Tool

Interactive terminal admin for managing the BBS database, sync peers, modules, and related configuration. The admin tool does not require a radio connection.

## Requirements

- Python 3.8+ with the project [virtual environment](README.md#setup-virtual-environment) activated
- `config.yml` in the project directory (copy from `example_config.yml` if needed)

## Starting the admin tool

```bash
python rsmesh-bbs_admin.py
```

| Flag | Purpose |
|------|---------|
| `-v` / `--version` | Print version and exit |

On startup the tool initializes the database, seeds system configuration from `config.yml` when needed, backfills sync peer timestamps, and shows a splash screen before the main menu.

---

## Navigation basics

### Page header

Every screen shows a bold header on line 1:

- Main areas: `{board_name} SysAdmin : {screen title}`
- Splash screen: `{board_name} SysAdmin`

The application version is right-aligned on the same line (last character in column 79). Line 2 is a 79-character `=` separator.

`{board_name}` comes from `config.yml` → `bbs.board_name` (default: `RSNetwork BBS`).

### Menu screens

Numbered menus prompt with **`Option: `** at the bottom. Enter the option number. Invalid input shows an error and returns to the same menu after you press Enter.

Submenus always end with **`0. Back to {parent}`**.

### Paginated lists

Long lists use an 18-line content area with page navigation:

| Key | Action |
|-----|--------|
| `N` | Next page |
| `P` | Previous page |
| `Enter` | Back (view-only lists) |
| `X` | Back |

When a list supports record selection, the prompt includes a select instruction (for example `Enter ID to view or X=back:`). Empty Enter also returns to the previous menu on selectable lists.

### Record detail views

Detail screens show labeled fields as `  Label : value`. Multiline values are indented under the label. Press **Enter** or **`X`** to return.

### Form screens

Add and edit forms clear the screen and show prompts in bold. On edit screens, **Enter** keeps the current value unless noted otherwise.

### Multiline text input

Bulletin and mail content use:

```
Enter content (type END on its own line when finished):
```

Type lines of text, then type **`END`** on its own line to finish.

### Y/N fields

Throughout the admin tool, yes/no fields accept **`Y`** or **`N`** (case-insensitive). Any other value falls back to the shown default.

---

## Splash screen

Shown once at startup before the main menu.

**Display:**
- Centered board name banner
- Total bulletins
- Channels published / unpublished
- Total mail / unread mail
- Pending reconcile counts (bulletins, channels)
- Sync alerts: RS version peer count

**Prompt:** `Press Enter to continue...`

---

## Main menu

| Option | Menu |
|--------|------|
| `1` | System Status |
| `2` | Administration |
| `3` | Bulletins |
| `4` | Channels |
| `5` | Mail |
| `6` | Node Catalog |
| `7` | Mesh Nodes |
| `0` | Exit |

---

## System Status

Read-only summary of the BBS database. Shows the same counts as the splash screen, plus a comma-separated list of configured sync peer node IDs (or `none`).

Paginated view-only. Use `N` / `P` to move between pages, Enter or `X` to return.

---

## Administration

| Option | Submenu |
|--------|---------|
| `1` | System Configuration |
| `2` | Sysadmin Nodes |
| `3` | Sync Peers |
| `4` | Modules |
| `5` | Backup |
| `0` | Back to Main Menu |

Changes to sync peers and sysadmin nodes are picked up by a running BBS server on the next mesh message or background worker cycle.

### System Configuration

Manages the `sys_config` table (runtime settings seeded from `config.yml`).

| Option | Action |
|--------|--------|
| `1` | List Configuration |
| `2` | Add Configuration Entry |
| `3` | Edit Configuration Entry |
| `4` | Delete Configuration Entry |
| `5` | Export Configuration to config.yml |
| `0` | Back |

#### List Configuration

Each row: `{index}. Section: {section}  Key: {key}  Value: {value}`

#### Add Configuration Entry

| Prompt | Required |
|--------|----------|
| `Section (e.g. bbs, interface):` | Yes |
| `Key:` | Yes |
| `Value:` | No (may be empty) |

Fails if the section/key pair already exists.

#### Edit / Delete Configuration Entry

Select by **row number** from the list (1-based index shown in the list, not the database ID): `Enter row # or X=cancel:`

Edit prompts for Section, Key, and Value (Enter = keep current). Renaming section/key deletes the old entry and inserts the new one.

#### Export Configuration to config.yml

Requires at least one configuration entry. Confirmation:

```
This will overwrite config.yml. Continue? (Y/N) [N]:
```

Only **`Y`** writes the file.

### Sysadmin Nodes

Grants operator privileges on the mesh BBS (for example Urgent board posting when combined with `bbs.superuser_node` in `config.yml`).

| Option | Action |
|--------|--------|
| `1` | List Sysadmin Nodes |
| `2` | Add Sysadmin Node |
| `3` | Edit Sysadmin Node |
| `4` | Delete Sysadmin Node |
| `0` | Back |

#### List display

`ID: {id}  Short name: {short}  Node: {node_hex}`

#### Add Sysadmin Node

| Prompt | Required |
|--------|----------|
| `Short name:` | Yes |
| `Node ID (e.g. !9e9d8704):` | Yes |

#### Edit / Delete Sysadmin Node

Select: `Enter sysadmin ID or X=cancel:`

### Sync Peers

Configure remote BBS nodes for bulletin, mail, channel, and mesh-node synchronization. Set **Enabled** to **`N`** to pause all sync to and from a peer while it is offline for maintenance; the peer's sync flags are preserved and take effect again when re-enabled.

| Option | Action |
|--------|--------|
| `1` | List Sync Peers |
| `2` | Add Sync Peer |
| `3` | Edit Sync Peer |
| `4` | Delete Sync Peer |
| `5` | List Unsynced Data |
| `0` | Back |

#### List Sync Peers — fields per peer

**Line 1:** ID, Node, Name (if set), Protocol, Enabled (Y/N), optional `Alert: received RS v{version}`

**Line 2:** `In: bulletins {Y/N}  channels {Y/N}  Out: bulletins {Y/N}  channels {Y/N}`

**Line 3:** `Mail: {Y/N}  Mesh nodes: {Y/N}  Last heard: {relative time}`

RS version alerts appear when a peer sends a sync wire version that does not match the configured protocol.

#### Add / Edit Sync Peer — prompts

| Prompt | Default | Valid values / notes |
|--------|---------|----------------------|
| `BBS node (e.g. !17d7e4b7):` | — | Required Meshtastic node ID |
| `BBS name (optional):` | empty | Display name for lists |
| `Sync protocol (tc2/rsv1) [tc2]:` | `tc2` | **`tc2`** or **`rsv1`** |
| `Sync bulletins out (Y/N) [Y]:` | Y | Send bulletins to this peer |
| `Sync mail in/out (Y/N) [Y]:` | Y | Bidirectional mail sync |
| `Sync channels out (Y/N) [Y]:` | Y | Send published channels to this peer |
| `Sync mesh nodes out/in (Y/N) [Y]:` | Y | **Only for `rsv1`** — mesh node directory sync |
| `Ingest bulletins in (Y/N) [Y]:` | Y | Accept bulletins from this peer |
| `Ingest channels in (Y/N) [Y]:` | Y | Accept channel rows from this peer (always ingested as unpublished) |
| `Enabled (Y/N) [Y]:` | Y | Master on/off for this peer; **`N`** skips all outbound and inbound sync |

**Protocol behavior:**
- **`tc2`** — TC²-compatible pipe-delimited sync (`BULLETIN|`, `MAIL|`, etc.). Mesh node sync is forced to **`N`**.
- **`rsv1`** — RS wire format (`RS|1|TYPE|{json}`). Supports mesh node sync and RS version negotiation.

Duplicate `bbs_node` values are rejected on add.

#### List Unsynced Data

Read-only report of records not yet synced to all eligible peers. Grouped into **Bulletins**, **Mail**, and **Channels** sections.

Each entry shows ID, key fields, sync status (`pending sync` or `pending delete sync` for deleted bulletins), and **Pending peers** (peer names or `all peers`).

### Modules

| Option | Action |
|--------|--------|
| `1` | List Modules |
| `2` | Edit Module Flags |
| `3+` | Dynamic entries for enabled modules with an admin screen |
| `0` | Back |

#### List Modules — per module (2 lines)

- `ID: {id}  Name: {name}  Menu: {menu_option}`
- `Dir: {dir}  Enabled: {Y/N}  Schedule: {Y/N}`

Default registered modules:

| Name | Directory | Mesh menu | Enabled | Schedule |
|------|-----------|-----------|---------|----------|
| Node Info | `node_info` | `I` | Y | Y |
| Example Hello | `example_hello` | `E` | N | N |
| Fortune | `fortune` | `F` | Y | N |

Fortune has no admin screen. Node Info and Example Hello add submenu entries here when enabled.

#### Edit Module Flags

Select: `Enter module ID or X=cancel:`

| Prompt | Valid |
|--------|-------|
| `Enabled (Y/N) [{current}]:` | Y/N |
| `Schedule enabled (Y/N) [{current}]:` | Y/N |

#### Module admin submenus

Enabled modules with `modules/{dir}/{dir}_admin.py` appear as additional numbered options. See [Module admin screens](#module-admin-screens) below.

### Backup

Creates `backup/backup_{YYYYMMDDHHMMSS}.zip` with no further prompts.

The archive contains:
- SQL dumps of all `*.db` files in the project root and under `modules/*/`
- `config.yml` and all `modules/*/config.yml` files

Success message reports file count, SQL dump count, and config count.

---

## Bulletins

| Option | Action |
|--------|--------|
| `1` | List Bulletins |
| `2` | Add Bulletin |
| `3` | Edit Bulletin |
| `4` | Delete Bulletins |
| `5` | Review Reconcile Bulletins |
| `0` | Back |

### Valid board names

`General`, `Info`, `News`, `Urgent`

List view groups bulletins by board in order: Urgent, General, News, Info (other board names appended alphabetically).

**Urgent alerts:** When `bbs.send_urgent_alert_local` is `yes`, **Add Bulletin** to the Urgent board queues a mesh broadcast for the running server (not sent from the admin tool directly). **Edit Bulletin** never queues or sends an Urgent alert, including when the board is changed to Urgent. See README “Urgent board alerts” for `send_urgent_alert_local` and `send_urgent_alert_from_sync`.

### List Bulletins — per entry (2 lines)

- `ID, Poster, Subject, Date`
- `UID, Del: {Y/N}, Pinned: {Y/N}, Reconcile: {Y/N}, Sync: {label}`

**Detail view fields:** ID, Board, Poster, Date, Subject, Content, Unique ID, Deleted, Pinned, Delete Reconcile, Sync

### Add Bulletin

| Prompt | Required | Valid |
|--------|----------|-------|
| `Board:` | Yes | One of the valid board names |
| `Poster short name:` | Yes | |
| `Subject:` | Yes | |
| Multiline content | No | END-terminated |

When the board is **Urgent** and `bbs.send_urgent_alert_local` is `yes`, the server queues a mesh broadcast alert (delivered by the running BBS process, not from the admin tool).

### Edit Bulletin

Select: `Enter ID or X=cancel:`

Editable: Board, Poster short name, Subject, Pinned (Y/N). Optional content re-entry when `Edit content? (Y/N) [N]:` is **`Y`**. Saving resets sync status.

### Delete Bulletins

Select: `Enter ID(s) or X=cancel:` — comma-separated IDs allowed.

Soft delete (`deleted='Y'`). The running BBS server purges and syncs deletes to peers.

### Review Reconcile Bulletins

Lists bulletins with `delete_reconcile='Y'` pending operator review after a peer delete sync.

Select: `Enter bulletin ID or X=cancel:`

Action prompt: **`[R]estore bulletin [D]elete permanently [X] cancel:`**

| Input | Effect |
|-------|--------|
| `R` | Restore (clear deleted and reconcile flags) |
| `D` | Permanently delete |
| `X` | Cancel |

---

## Channels

| Option | Action |
|--------|--------|
| `1` | List Channels |
| `2` | Add Channel |
| `3` | Edit Channel |
| `4` | Delete Channels |
| `5` | Export to CSV |
| `6` | Import from CSV |
| `7` | Review Reconcile Channels |
| `0` | Back |

Channels added through the admin tool default to **published** (`publish=Y`) and are eligible for mesh display and peer sync.

### List Channels — per entry (2 lines)

- `ID, Name, Sync: {label}, Publish: {Y/N}`
- `PSK, Del: {Y/N}, Reconcile: {Y/N}`

**Detail view fields:** ID, Name, PSK, Publish, Unique ID, Deleted, Delete Reconcile, Sync

### Add Channel

| Prompt | Required |
|--------|----------|
| `Channel name:` | Yes |
| `Channel PSK:` | Yes |

### Edit Channel

Select: `Enter ID or X=cancel:`

Editable: Channel name, Channel PSK, Publish (Y/N). Setting Publish to **`Y`** marks the channel for outbound sync. Setting Publish to **`N`** excludes it from sync.

### Delete Channels

Select: `Enter ID(s) or X=cancel:` — comma-separated IDs allowed. Soft delete.

### Export / Import CSV

Default filename: `channels.csv`  
Prompt: `Enter filename (full path allowed) [channels.csv]:`

**CSV columns:** `name`, `psk`, `publish`, `synced`, `unique_id`

| Column | Required on import | Default if omitted |
|--------|-------------------|-------------------|
| `name` | Yes | — |
| `psk` | Yes | — |
| `publish` | No | `Y` |
| `synced` | No | `N` |
| `unique_id` | No | generated |

Import mode: **`[R]eplace existing data or [A]ppend to existing data? [A]:`**

| Input | Effect |
|-------|--------|
| `R` | Replace all channels |
| `A` or Enter | Append/merge (update matching names) |
| Other | Cancelled |

Import summary reports Inserted, Updated, Unchanged, and Skipped rows (up to 5 error lines shown).

### Review Reconcile Channels

Same workflow as bulletin reconcile. Action prompt: **`[R]estore channel [D]elete permanently [X] cancel:`**

---

## Mail

| Option | Action |
|--------|--------|
| `1` | List Mail |
| `2` | Send Mail |
| `3` | Edit Mail |
| `4` | Delete Mail |
| `0` | Back |

### List Mail — per entry (2 lines)

- `ID, To: {short or hex}, From: {short or hex}, Sync: {label}`
- `Subject: {subject}`

**Detail view fields:** ID, Sender Hex, Sender Short Name, Recipient Hex, Recipient Short Name, Date, Subject, Content, Unique ID, Read (Y/N), Sync

### Send Mail

| Prompt | Required |
|--------|----------|
| `Sender node ID (e.g. !9e9d8704):` | Yes |
| `Sender short name:` | Yes |
| `Recipient node ID or short name:` | Yes |
| `Subject:` | Yes |
| Multiline content | No |

### Edit Mail

Select: `Enter ID or X=cancel:`

Editable: Sender node ID, Sender short name, Recipient, Subject. Optional content re-entry. Saving resets sync status.

### Delete Mail

Select: `Enter ID(s) or X=cancel:` — comma-separated IDs allowed.

**Hard delete** (record removed immediately). The running server syncs deletes to peers.

---

## Node Catalog

Operator directory of known nodes with keys and admin flags. Distinct from **Mesh Nodes**, which tracks nodes observed on the mesh.

| Option | Action |
|--------|--------|
| `1` | List Node Catalog |
| `2` | Add Node Catalog Entry |
| `3` | Edit Node Catalog Entry |
| `4` | Delete Node Catalog Entry |
| `5` | Export to CSV |
| `6` | Import from CSV |
| `0` | Back |

### List — per entry

`ID, Short, Long, Node: {hex}, Admin: {Y/N}`

Admin is **`Y`** when `mesh_admin=Y` or `bbs_admin=Y`.

**Detail view fields:** ID, Short Name, Long Name, Node Hex Username, Mesh Admin, BBS Admin, BBS Mail Forward To, Has GPS, Public Key, Private Key, BLE PIN, Hardware, Comment, Created, Updated

### Add Node Catalog Entry

| Prompt | Default | Required |
|--------|---------|----------|
| `Long name:` | — | Yes |
| `Short name:` | — | Yes |
| `Node hex username (e.g. !9e9d8704):` | — | Yes |
| `Mesh admin (Y/N) [N]:` | N | Y/N |
| `BBS admin (Y/N) [N]:` | N | Y/N |
| `BBS mail forward to (optional):` | — | No |
| `Has GPS (Y/N) [N]:` | N | Y/N |
| `Public key:` | — | Yes |
| `Private key (optional):` | — | No |
| `BLE PIN [123456]:` | 123456 | No |
| `Hardware (optional):` | — | No |
| `Comment (optional):` | — | No |

Adding or changing `bbs_admin` syncs the `sysadmin_nodes` table.

### Edit / Delete Node Catalog Entry

Select: `Enter catalog ID or X=cancel:` (delete supports comma-separated IDs).

### Export / Import CSV

Default filename: `node_catalog.csv`

**CSV columns:** `long_name`, `short_name`, `node_hex_username`, `mesh_admin`, `bbs_admin`, `bbs_mail_forward_to`, `has_gps`, `public_key`, `private_key`, `ble_pin`, `hardware`, `comment`, `created`, `updated`

**Required on import:** `long_name`, `short_name`, `node_hex_username`, `public_key`

**Y/N columns:** `mesh_admin`, `bbs_admin`, `has_gps` (invalid values default to `N`)

Import mode: Replace (`R`) or Append (`A`, default).

---

## Mesh Nodes

Tracks nodes seen on the mesh (for sync and resolution). Populated by the BBS from live traffic and RS sync; can also be managed manually here.

| Option | Action |
|--------|--------|
| `1` | List Mesh Nodes |
| `2` | Add Mesh Node |
| `3` | Edit Mesh Node |
| `4` | Delete Mesh Node |
| `5` | Export to CSV |
| `6` | Import from CSV |
| `7` | Purge Mesh Nodes |
| `0` | Back |

### List — per entry

`Node: {id}  Short: {name or -}  Long: {name or -}  Seen: {relative time}`

**Detail view fields:** Node ID, Short Name, Long Name, Last Heard (timestamp), Last Heard (relative), Last Updated

### Add Mesh Node

| Prompt | Required |
|--------|----------|
| `Node hex ID (e.g. !9e9d8704):` | Yes |
| `Short name (optional):` | No |
| `Long name (optional):` | No |
| `Last heard unix timestamp (optional):` | No |

Fails if the node ID already exists.

### Edit / Delete Mesh Node

Select: `Enter node ID or X=cancel:`

### Export / Import CSV

Default filename: `mesh_nodes.csv`

**CSV columns:** `node_id`, `short_name`, `long_name`, `last_heard`

**Required on import:** `node_id`

Replace mode clears all mesh nodes and mesh-node sync peer records before import.

### Purge Mesh Nodes

Confirmation: `Delete ALL mesh nodes? This cannot be undone. (Y/N) [N]:`

Only **`Y`** deletes every row.

---

## Module admin screens

Reached from **Administration → Modules** when the module is enabled and provides an admin file.

### Node Info

**Title:** Node Info

| Option | Action |
|--------|--------|
| `1` | List Node Info |
| `0` | Back to Modules |

Data comes from `modules/node_info/node_info.db` (not the main BBS database).

**Per node (3 lines):**
- `{short} - {long} [{node_id}]  Seen: {relative}`
- `Signal: {GOOD|FAIR|POOR|UNKNOWN} (SNR {value|UNK} RSSI {value|UNK})  Hops: {n|UNK}  Loc: {lat,lon|Unknown}`
- `Updated: {timestamp}`

Paginated, view-only.

### Example Hello

**Title:** Example Hello (only when module is enabled)

| Option | Action |
|--------|--------|
| `1` | List Visits |
| `0` | Back to Modules |

**Per visit:** `{short_name}  {timestamp}  greeting {pending|sent}`

Paginated, view-only.

---

## Reference

### Sync status labels

Shown on bulletin, mail, and channel list/detail views:

| Label | Meaning |
|-------|---------|
| `Y` | Fully synced to all eligible **enabled** peers (or no eligible peers configured) |
| `N` | Not synced to any eligible peer |
| `n/total` | Synced to *n* of *total* eligible enabled peers |
| `*` | Channels only — unpublished (`publish=N`); not synced |

### Sync protocols

| Protocol | Wire format | Mesh node sync |
|----------|-------------|----------------|
| `tc2` | Pipe-delimited (`BULLETIN|`, `MAIL|`, …) | Not supported |
| `rsv1` | `RS\|1\|TYPE\|{json}` | Supported when enabled per peer |

### Node ID format

Meshtastic hex node IDs with a leading `!`, for example `!9e9d8704` or `!17d7e4b7`.

### Delete behavior summary

| Entity | Delete type | Notes |
|--------|-------------|-------|
| Bulletins | Soft | Marked deleted; server purges and syncs |
| Channels | Soft | Marked deleted; server purges and syncs |
| Mail | Hard | Removed immediately; server syncs delete |
| Mesh nodes | Hard | Single-node delete or full purge |
| Sync peers | Hard | Removed from configuration |
| Sysadmin nodes | Hard | Removed from table |

### Reconcile workflow

When a sync peer deletes a bulletin or channel, the local copy is marked `delete_reconcile='Y'` instead of being removed immediately. Use **Review Reconcile** under Bulletins or Channels to restore or permanently delete each pending record.

### Complete menu tree

```
Splash Screen
└── Main Menu
    ├── 1. System Status
    ├── 2. Administration
    │   ├── 1. System Configuration
    │   ├── 2. Sysadmin Nodes
    │   ├── 3. Sync Peers
    │   ├── 4. Modules
    │   │   ├── [Node Info] → List Node Info
    │   │   └── [Example Hello] → List Visits (if enabled)
    │   └── 5. Backup
    ├── 3. Bulletins
    ├── 4. Channels
    ├── 5. Mail
    ├── 6. Node Catalog
    ├── 7. Mesh Nodes
    └── 0. Exit
```
