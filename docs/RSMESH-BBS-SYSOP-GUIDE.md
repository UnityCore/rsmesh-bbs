# RSMesh BBS Sysop Guide

Release 1.1

Operator reference for running and configuring RSMesh BBS: the mesh client simulator, configuration, node and channel directories, background workers, shipped modules, and the interactive admin tool.

## Table of contents

- [Mesh client (no radio)](#mesh-client-no-radio)
- [Configuration reference](#configuration-reference)
- [Urgent board alerts](#urgent-board-alerts)
- [Pinned bulletins](#pinned-bulletins)
- [Mail forwarding](#mail-forwarding)
- [Node directory](#node-directory)
  - [Short-name and hex ID resolution](#short-name-and-hex-id-resolution)
  - [Mesh nodes vs Node Info](#mesh-nodes-vs-node-info)
  - [Node catalog (operator reference)](#node-catalog-operator-reference)
- [Channel directory](#channel-directory)
  - [PSK model](#psk-model)
  - [Staged publishing](#staged-publishing)
  - [Sync peer trust](#sync-peer-trust)
- [Operator concepts](#operator-concepts)
- [Mesh main menu (cached file)](#mesh-main-menu-cached-file)
  - [Default layout](#default-layout)
  - [Operator customization](#operator-customization)
  - [Module menu letters (per-menu rules)](#module-menu-letters-per-menu-rules)
  - [When the menu file is regenerated](#when-the-menu-file-is-regenerated)
  - [M[o]dules on the main menu](#modules-on-the-main-menu)
- [Shipped modules (mesh menus)](#shipped-modules-mesh-menus)
- [Starting the admin tool](#starting-the-admin-tool)
- [Navigation basics](#navigation-basics)
  - [Page header](#page-header)
  - [Menu screens](#menu-screens)
  - [Paginated lists](#paginated-lists)
  - [Record detail views](#record-detail-views)
  - [Form screens](#form-screens)
  - [Multiline text input](#multiline-text-input)
  - [Y/N fields](#yn-fields)
- [Splash screen](#splash-screen)
- [Main menu](#main-menu)
- [System Status](#system-status)
- [Administration](#administration)
  - [Core Services](#core-services)
  - [Regenerate Main Menu](#regenerate-main-menu)
  - [System Configuration](#system-configuration)
    - [Section menus](#section-menus)
    - [Export Configuration to config.yml](#export-configuration-to-configyml)
  - [Sysadmin Nodes](#sysadmin-nodes)
    - [List display](#list-display)
    - [Add Sysadmin Node](#add-sysadmin-node)
    - [Edit / Delete Sysadmin Node](#edit--delete-sysadmin-node)
  - [Sync Peers](#sync-peers)
    - [List Sync Peers — fields per peer](#list-sync-peers--fields-per-peer)
    - [Add / Edit Sync Peer — prompts](#add--edit-sync-peer--prompts)
    - [List Unsynced Data](#list-unsynced-data)
  - [Modules](#modules)
    - [List Modules — per module (2 lines)](#list-modules--per-module-2-lines)
    - [Edit Module Flags](#edit-module-flags)
    - [Module admin submenus](#module-admin-submenus)
  - [Backup](#backup)
- [Bulletins](#bulletins)
  - [Valid board names](#valid-board-names)
  - [List Bulletins — per entry (2 lines)](#list-bulletins--per-entry-2-lines)
  - [Add Bulletin](#add-bulletin)
  - [Edit Bulletin](#edit-bulletin)
  - [Delete Bulletins](#delete-bulletins)
  - [Review Reconcile Bulletins](#review-reconcile-bulletins)
- [Channels](#channels)
  - [List Channels — per entry (2 lines)](#list-channels--per-entry-2-lines)
  - [Add Channel](#add-channel)
  - [Edit Channel](#edit-channel)
  - [Delete Channels](#delete-channels)
  - [Export / Import CSV](#export--import-csv)
  - [Review Reconcile Channels](#review-reconcile-channels)
- [Mail](#mail)
  - [List Mail — per entry (2 lines)](#list-mail--per-entry-2-lines)
  - [Send Mail](#send-mail)
  - [Edit Mail](#edit-mail)
  - [Delete Mail](#delete-mail)
- [Node Catalog](#node-catalog)
  - [List — per entry](#list--per-entry)
  - [Add Node Catalog Entry](#add-node-catalog-entry)
  - [Edit / Delete Node Catalog Entry](#edit--delete-node-catalog-entry)
  - [Export / Import CSV](#export--import-csv-1)
- [Mesh Nodes](#mesh-nodes)
  - [List — per entry](#list--per-entry-1)
  - [Add Mesh Node](#add-mesh-node)
  - [Edit / Delete Mesh Node](#edit--delete-mesh-node)
  - [Export / Import CSV](#export--import-csv-2)
  - [Purge Mesh Nodes](#purge-mesh-nodes)
- [Module admin screens](#module-admin-screens)
  - [Node Info](#node-info)
  - [Example Hello](#example-hello)
- [Reference](#reference)
  - [Sync status labels](#sync-status-labels)
  - [Sync protocols](#sync-protocols)
  - [Node ID format](#node-id-format)
  - [Delete behavior summary](#delete-behavior-summary)
  - [Reconcile workflow](#reconcile-workflow)
  - [Complete menu tree](#complete-menu-tree)

## Mesh client (no radio)

`rsmesh-bbs_client.py` simulates a mesh handset in-process — useful for testing menus, mail, and bulletins without a Meshtastic device or running server. It uses the same `rsmesh-bbs.db` and `config.yml` as the server (for board name and other BBS settings), but drives the BBS command handlers directly through a mock interface (no radio, no PyPubSub).

Simulated handset identity (`node_id`, `short_name`, `long_name`) and the in-process virtual BBS radio (`virtual_node_id`, `virtual_short_name`, `virtual_long_name`) are configured in `config_client.yml`. Copy the starter file before your first run:

```bash
cp example_config_client.yml config_client.yml
```

With the [virtual environment](../README.md#setup-virtual-environment) activated:

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
| `--verbose` / `-v` | Print `(no reply)` when the BBS sends no response (debugging) |

During multiline mail compose, the BBS often sends no per-line reply until you type `END`. By default the client stays silent for those empty turns; use `--verbose` if you want to see `(no reply)` for each blank response.

Example `config_client.yml`:

```yaml
client:
  node_id: "!0c0ffee0"
  short_name: COFY
  long_name: BBS Test Client

server:
  virtual_node_id: "!aabbcc00"
  virtual_short_name: BBS0
  virtual_long_name: RSMesh Virtual Radio
```

The `client` section is your simulated handset. The `server` section is the mock BBS radio the client talks to locally (not a real Meshtastic device). `virtual_node_id` must be a Meshtastic-style hex ID with a leading `!`; the node number is derived from it automatically. If you omit `virtual_long_name`, it defaults to `RSMesh Virtual Radio`.

Command-line flags override `client` values from `config_client.yml` when you need a one-off handset identity. Virtual BBS radio settings are read from the config file only. The board banner still comes from `config.yml` in the project directory (see [Configuration reference](#configuration-reference)).

Type messages as you would from a handset (single-letter menu commands such as `B`, `M`, `R`). See the [User Guide](RSMESH-BBS-USER-GUIDE.md) for menus and flows. Press Enter or type `X` for the main menu. Ctrl+C or Ctrl+D to quit.

The pytest `mesh_client` fixture in `tests/conftest.py` uses the same harness against a temporary database. See [Tests](RSMESH-BBS-DEVELOPER-GUIDE.md#tests) in the Developer Guide.

## Configuration reference

| Setting | Location | Notes |
|---------|----------|-------|
| Simulated handset identity | `config_client.yml` `client` | `node_id`, `short_name`, and `long_name` (default long name: `BBS Test Client`) for `rsmesh-bbs_client.py` (see `example_config_client.yml`) |
| Virtual BBS radio (mesh client) | `config_client.yml` `server` | `virtual_node_id`, `virtual_short_name`, and `virtual_long_name` (default long name: `RSMesh Virtual Radio`) for the in-process mock radio used by `rsmesh-bbs_client.py` |
| Board name, superuser, event bus topic | `config.yml` `bbs` | Banner text, Urgent board permission, and PyPubSub topic for incoming radio packets (`eventbus_topic`, default `meshtastic.receive`) |
| Urgent mesh alerts (local) | `config.yml` `bbs` `send_urgent_alert_local` | `true`/`false` — broadcast on primary channel when an Urgent bulletin is posted on this node (default `false`) |
| Urgent mesh alerts (sync) | `config.yml` `bbs` `send_urgent_alert_from_sync` | `true`/`false` — broadcast when an Urgent bulletin is ingested from a sync peer (default `false`) |
| Core services (defaults) | `config.yml` `bbs` `core_bulletins`, `core_mail`, `core_channels` | `true`/`false` — seeded into `sys_config` on first run; toggled live under **Administration → Core Services** in the admin tool |
| Mail on main menu (default off) | `config.yml` `bbs` `mail_commands_on_main_menu` | `true`/`false` — when `true` and Mail is enabled, show `[R]ead Mail` / `[S]end Mail` on the mesh main menu and omit `[M]ail`; toggled live under **Core Services** option `4` |
| Radio interface | `config.yml` `interface` | `serial` or `tcp`; set `port` or `hostname` as needed |
| Peer sync interval | `config.yml` `schedule` | Minutes between retries for unsynced records |
| Module schedule tick | `config.yml` `schedule` | Minutes between module schedule worker runs (`module_exec_minutes`) |
| Node Info purge / scan | `modules/node_info/config.yml` | Per-module settings (`purge_minutes`, `scan_interval_minutes`) |
| Deleted bulletin purge interval | `config.yml` `schedule` | Minutes between purge runs for bulletins marked deleted (`sync_purge_minutes`) |
| Mesh bulletin display age | `config.yml` `schedule` | Days of non-pinned bulletins shown on mesh boards (`bulletin_display_age_days`) |
| Sync peers | `sync_peers` table | Configure with `rsmesh-bbs_admin.py`. Protocols: `tc2`, `rsv1` (and future `rsv2`, …). See [Sync wire formats](RSMESH-BBS-DEVELOPER-GUIDE.md#sync-wire-formats). |
| Sysadmin nodes | `sysadmin_nodes` table | Configure with `rsmesh-bbs_admin.py` (also seeded from `superuser_node` and node catalog) |

See `example_config.yml` for a commented starter BBS configuration and `example_config_client.yml` for mesh client handset and virtual radio identity.

## Urgent board alerts

The **Urgent** bulletin board is restricted to sysadmin nodes for posting. When enabled, new Urgent bulletins can trigger a mesh-wide broadcast on the radio primary channel (channel index 0).

| Setting | Default | Behavior |
|---------|---------|----------|
| `send_urgent_alert_local` | `false` | Broadcast when a user posts Urgent on this BBS, or when an operator adds an Urgent bulletin in the admin tool |
| `send_urgent_alert_from_sync` | `false` | Broadcast when an Urgent bulletin arrives from a sync peer |

Both settings use `true` or `false`. Changes take effect immediately via `sys_config` (admin tool or server restart seeding from `config.yml`).

**Local posts** from mesh users are sent immediately when `send_urgent_alert_local` is `true`. **Admin Add Bulletin** queues the alert in the database; the running server delivers it on the main loop (typically within about one second). Editing a bulletin does not queue or send an alert.

If `send_urgent_alert_local` is turned off while alerts are queued, the server drops queued rows without sending. Queued alerts are only created when the setting is `true` at add time.

Before sending a queued alert, the server verifies the bulletin still exists and is still on the Urgent board.

## Pinned bulletins

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

**Node Info** is an **optional module** (enabled by default, but you can turn it off under **Administration → Modules**). It keeps a separate, richer telemetry database: SNR, RSSI, hop count, GPS coordinates, channel-quality estimates, and related fields gathered from overheard packets. Mesh users reach it from **M[o]dules** (`O` on the main menu) for node counts and statistics; sysadmins can list detailed rows. Think of Node Info as an **enhanced telemetry reference**, not a requirement for core BBS features.

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
| Peer sync | `peer_sync_minutes` | Retries unsynced bulletins, mail, and published channels to eligible sync peers (skips types disabled under **Core Services**) |
| Purge | `sync_purge_minutes` | Reloads peer/sysadmin config; purges soft-deleted bulletins/channels and pushes delete sync (skips types disabled under **Core Services**) |
| Module schedule | `module_exec_minutes` | Runs enabled module scheduled tasks (Node Info scan/purge, etc.) |

**Core Services** — Under **Administration → Core Services**, operators can enable or disable the built-in Bulletins, Mail, and Channels features. Settings live in `sys_config` (`bbs.core_bulletins`, `bbs.core_mail`, `bbs.core_channels`) and are seeded from `config.yml` on upgrade (default enabled). When a service is off, the admin tool hides its top-level menu, inbound peer sync for that record type is skipped, and background sync/purge workers omit that type. On the mesh main menu, the matching option (`[B]ulletins`, `[M]ail`, or `[C]hannels`) is hidden and that letter becomes available for an enabled module.

**Soft delete** — Admin **Delete Bulletins** / **Delete Channels** (and mesh sysadmin bulletin delete) set `deleted='Y'`. The purge worker removes them locally and syncs deletes to peers. **List Unsynced Data** in the admin tool shows records still pending peer sync.

**Reconcile** — When a sync peer deletes a bulletin or channel, your copy is marked `delete_reconcile='Y'` until an operator restores or permanently deletes it (**Review Reconcile** menus).

**Sysconfig** — Many `config.yml` values are copied into the `sys_config` table on first run. The admin tool can edit them live; **Export Configuration to config.yml** writes the database values back to `config.yml`.

## Mesh main menu (cached file)

Mesh users see a two-part main menu on every `HELP` / return-to-menu:

1. **Title line** — built at display time: `= {board_name} : {mail_count} Msg(s) =`
2. **Option rows** — read from `mesh_ui/main_menu.txt` (no title line in the file)

The server does not rebuild the option rows on every mesh request. It reads the cached file when valid, or falls back to an auto-generated body.

### Default layout

| Row | Keys (Mail submenu layout — default) | Keys (Mail on main menu layout) |
|-----|--------------------------------------|----------------------------------|
| 1 | `[B]ulletins` / `[C]hannels` | `[B]ulletins` / `[C]hannels` |
| 2+ | Enabled modules promoted to the main menu (see below), if any | Same |
| next | `[M]ail`, then M[o]dules (`O`) when shown | `[R]ead Mail` / `[S]end Mail`, then M[o]dules (`O`) when shown |
| last | `E[X]IT` | `E[X]IT` |

The two mail layouts are **mutually exclusive**. Only one appears on the mesh main menu at a time.

- **Mail submenu layout (default)** — **`[M]ail`** is on the main menu. It opens a second screen with **`[R]ead Mail`**, **`[S]end Mail`**, and **`E[X]IT`**. `R` and `S` are not main-menu keys in this mode.
- **Mail on main menu layout** — Under **Administration → Core Services**, enable **Display Mail commands on Main Menu** (option `4`). The main menu shows **`[R]ead Mail`** and **`[S]end Mail`** directly; **`[M]ail` is not shown** and pressing **`M`** on the main menu does not open the mail submenu (it redraws the main menu). Users open mail with **`R`** or **`S`** from the top level. Empty inbox and other mail exits return to the main menu rather than the mail submenu. While this option is on, **`M`** is not reserved for Mail and may be assigned to a module; **`R`** and **`S`** are reserved on the main menu instead.
- **`[B]ulletins`**, **`[M]ail`**, and **`[C]hannels`** are each removed from the main menu when the matching core service is off (**Administration → Core Services**). The freed main-menu letter can be assigned to an enabled module; see [Module menu letters (per-menu rules)](#module-menu-letters-per-menu-rules).
- **M[o]dules** (`O`) is omitted when there are no enabled modules, or when no enabled module needs the aggregator submenu (see [M[o]dules on the main menu](#modules-on-the-main-menu)).

### Operator customization

You may edit `mesh_ui/main_menu.txt` directly for branding or layout. Treat it as a **display-only** override: menu keys and routing still come from core services, the `modules` table, and code.

Constraints:

- The title line plus file body must fit in a **single 200-byte** mesh packet. If the file is empty, invalid, or too large, the server ignores it and shows an auto-generated body instead.
- Module `menu_option` letters must not collide with keys on menus where users select a module. See [Module menu letters (per-menu rules)](#module-menu-letters-per-menu-rules).

### Module menu letters (per-menu rules)

Each module has a one-letter **`menu_option`** in the `modules` table. The BBS routes keys based on **which menu the user is in** (main menu, mail submenu, M[o]dules submenu, bulletin boards, and so on). A letter used in one menu does **not** block modules from using the same letter on a different menu.

Module `menu_option` validation only checks menus where a module can be chosen by letter: the **main menu** and the **M[o]dules** submenu.

**Reserved on the main menu** (modules cannot use these letters)

| Letter | Used for |
|--------|----------|
| `O` | M[o]dules |
| `X` | E[X]IT |

**Also reserved on the main menu while the matching core service is enabled**

| Core service | Main-menu letter | Free for modules when service is OFF |
|--------------|------------------|--------------------------------------|
| Bulletins | `B` | `B` |
| Channels | `C` | `C` |
| Mail (submenu layout) | `M` | `M` |
| Mail (on main menu layout) | `R`, `S` | `R`, `S` |

When a core service is **off**, its main-menu entry is hidden and that letter can be assigned to an enabled module. An enabled module using a freed `B`, `C`, or `M` appears on the main menu automatically (no **Show on main menu** needed).

**Not reserved for modules** (different menu — no conflict)

| Menu | Core keys | Available to modules? |
|------|-----------|------------------------|
| Mail submenu (after `M`, default mail layout) | `R`, `S`, `X` | Yes — `R` and `S` may be module letters when Mail uses the `[M]ail` submenu |
| Bulletin boards (after `B`) | `G`, `I`, `N`, `U`, `X` | Yes — e.g. a module may use `G` while Bulletins is on |
| Channel directory (after `C`) | `V`, `P`, `X` | Yes |
| M[o]dules submenu | module letters, `X` | `X` is reserved (exit); other letters are module slots |

**Mail example:** With Mail **enabled** and the default submenu layout, `M` is reserved on the main menu; `R` and `S` may still be module letters because they only apply after `M`. With **Display Mail commands on Main Menu** enabled, `[M]ail` is omitted from the main menu, `R` and `S` are reserved on the main menu, and `M` may be assigned to a module. With Mail **disabled**, `M` is also available for modules regardless of the mail layout option.

### When the menu file is regenerated

| Trigger | When `main_menu.txt` is rewritten |
|---------|-----------------------------------|
| **Leaving Administration** | Once, after any changes in that session that affect the mesh menu (Core Services toggles, mail layout option, module flags, suppress setting) |
| **Administration → Regenerate Main Menu** | Immediately on that action |
| **Server or client startup** | Only when `main_menu.txt` is missing or invalid (oversized/empty); valid operator customizations are preserved |

While you remain inside **Administration**, individual toggles update the database immediately but **do not** rewrite `main_menu.txt` until you back out to the admin main menu. That batches several changes into one rewrite and avoids overwriting `main_menu.old` repeatedly.

Each regeneration copies the current `main_menu.txt` to **`mesh_ui/main_menu.old`** before writing the new body. If you had a custom menu file, `.old` keeps that previous version (not intermediate drafts from toggling inside Administration).

### M[o]dules on the main menu

**No enabled modules** — M[o]dules is never shown on the main menu, regardless of the suppress toggle. There is nothing to list in an empty aggregator submenu.

**Promote a module** — **Administration → Modules → Edit Module Flags** → **Show on main menu (Y/N)**. When `Y`, the module’s menu letter appears on the main menu; users can open it without going through M[o]dules.

**Suppress Modules submenu** — **Administration → Modules → Suppress Modules Submenu**. Stored as `bbs.suppress_modules_menu` in `sys_config`.

When suppress is **off** (default), M[o]dules stays on the main menu and lists every enabled module, even when those modules also appear on the main menu. That is intentional: users can open a module from its main-menu letter or from M[o]dules. If you promote every **enabled** module to the main menu and do **not** want the redundant M[o]dules entry, turn suppress **on**.

When suppress is **on**:

- Modules already on the main menu are not listed again under M[o]dules.
- M[o]dules is **hidden** when every **enabled** module is on the main menu (disabled modules are ignored for this decision).
- M[o]dules stays visible if any **enabled** module still needs the aggregator submenu.

The admin tool **refuses to turn suppress on** while any enabled module is not on the main menu. Those modules would only be reachable through M[o]dules; suppressing it would hide them from mesh users. Promote each enabled module (**Show on main menu** = `Y`) or disable it before enabling suppress.

## Shipped modules (mesh menus)

Enable under **Administration → Modules**. By default, users open modules from **M[o]dules** (`O`) on the main menu. Set **Show on main menu** to `Y` on a module to expose its menu letter on the top-level menu instead.

| Module | Menu option | Mesh actions |
|--------|-------------|--------------|
| **Fortune** | `F` (default) | Shows a random fortune on entry; any message fetches another; `X` exits |
| **Node Info** | (per `modules` table) | `[N]odes` counts by time window, `[H]ardware` model counts, `[R]oles` role counts; sysadmins also get `[L]ist Nodes` (detailed signal/GPS lines) |
| **Example Hello** | (disabled by default) | Greets on entry; demonstrates visits DB and scheduled greetings |
| **BBS List** | `L` (default) | Browse known mesh BBS boards; `sync=Y` marks sync interest; `LocalPost` / `RemotePost` shows entry source; enter node ID for details; `[A]ll` / `[S]ync` lists |

Fortune has no admin screen. Node Info admin is view-only (**List Node Info**). **BBS List** admin supports register-this-BBS, add/edit/delete entries, and sync-interested list. See [Module development](RSMESH-BBS-DEVELOPER-GUIDE.md#modules) in the Developer Guide.

---

## Starting the admin tool

```bash
python rsmesh-bbs_admin.py
```

| Flag | Purpose |
|------|---------|
| `-v` / `--version` | Print version and exit |

On startup the tool initializes the database, seeds system configuration from `config.yml` when needed, backfills sync peer timestamps, and shows a splash screen before the main menu.

Sync peer and sysadmin changes made in the admin tool are picked up by the running server automatically on the next mesh message or background worker cycle.

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
- Core Services: comma-separated list of enabled services (`Bulletins`, `Mail`, `Channels`), or `None` when all are off

**Prompt:** `Press Enter to continue...`

---

## Main menu

| Option | Menu |
|--------|------|
| `1` | System Status |
| `2` | Administration |
| `3`–`5` | Bulletins, Channels, Mail (only when the matching core service is enabled; see [Core Services](#core-services)) |
| next | Node Catalog |
| next | Mesh Nodes |
| `0` | Exit |

Option numbers after **Administration** are assigned in order: enabled core services first (Bulletins, then Channels, then Mail), then Node Catalog, then Mesh Nodes. For example, with all three core services on, Node Catalog is `6` and Mesh Nodes is `7`; with Mail disabled, Node Catalog is `5` and Mesh Nodes is `6`.

---

## System Status

Read-only summary of the BBS database. Shows the same counts as the splash screen, plus a comma-separated list of configured sync peer node IDs (or `none`), and the enabled core services line.

Paginated view-only. Use `N` / `P` to move between pages, Enter or `X` to return.

---

## Administration

| Option | Submenu |
|--------|---------|
| `1` | System Configuration |
| `2` | Core Services |
| `3` | Regenerate Main Menu |
| `4` | Sysadmin Nodes |
| `5` | Sync Peers |
| `6` | Modules |
| `7` | Backup |
| `0` | Back to Main Menu |

Changes to sync peers and sysadmin nodes are picked up by a running BBS server on the next mesh message or background worker cycle. Core Services toggles take effect immediately for admin menus and background sync/purge workers; the cached mesh main menu file is updated when you **leave Administration** (see [Mesh main menu (cached file)](#mesh-main-menu-cached-file)).

### Core Services

Enable or disable the built-in Bulletins, Mail, and Channels features without uninstalling modules or editing raw `sys_config` rows.

| Option | Setting |
|--------|---------|
| `1` | Bulletins |
| `2` | Mail |
| `3` | Channels |
| `4` | Display Mail commands on Main Menu |
| `0` | Back to Administration |

Options `1`–`3` enable or disable each core service. Each row shows **Enabled** or **Disabled**; select a row to toggle it. Service toggles are stored in `sys_config` as `bbs.core_bulletins`, `bbs.core_mail`, and `bbs.core_channels` (seeded from `config.yml` on upgrade).

**Option `4` — Display Mail commands on Main Menu** (`bbs.mail_commands_on_main_menu`, default **Disabled**):

- **Disabled (default):** Main menu shows **`[M]ail`**; Read/Send are on the mail submenu after the user presses `M`.
- **Enabled:** Main menu shows **`[R]ead Mail`** and **`[S]end Mail`**; **`[M]ail` is omitted** from the main menu and `M` does not open the mail submenu. Only applies while Mail (option `2`) is enabled; the setting is stored either way but has no mesh effect when Mail is off.
- Toggling option `4` regenerates the cached mesh main menu when you leave **Administration** (same as other Core Services changes). See [Default layout](#default-layout) for the two mail layouts.

When a service is disabled:

- Its entry disappears from the admin **Main Menu** (Bulletins, Channels, or Mail).
- Inbound peer sync for that record type is skipped.
- Background peer sync, outbound sync, and purge workers omit that type.
- **List Unsynced Data** omits records for that type.

On the mesh main menu, `[B]ulletins`, `[M]ail`, and `[C]hannels` are each hidden when the matching core service is off. The freed main-menu letter (`B`, `C`, or `M`) becomes available for modules (see [Module menu letters (per-menu rules)](#module-menu-letters-per-menu-rules)).

Toggling a service does not rewrite `mesh_ui/main_menu.txt` on each keypress; the cached mesh menu body is regenerated once when you leave **Administration**.

### Regenerate Main Menu

Rewrites `mesh_ui/main_menu.txt` from the current configuration **immediately**, copying the previous file to `mesh_ui/main_menu.old` first. Use this after editing the menu file by hand, or to force a fresh auto-generated body without changing other settings.

### System Configuration

Edits required runtime settings stored in the `sys_config` table. Keys and defaults come from `example_config.yml`; startup seeds any missing rows from that file (using values from `config.yml` when present).

| Option | Section |
|--------|---------|
| `1` | BBS |
| `2` | Interface |
| `3` | Schedule |
| `4` | Export Configuration to config.yml |
| `0` | Back to Administration |

Core service toggles (`core_bulletins`, `core_mail`, `core_channels`, `mail_commands_on_main_menu`) and `suppress_modules_menu` are **not** edited here — use **Core Services** and **Modules** instead.

#### Section menus

Each section menu uses the page header **`System Configuration : {section}`** (for example `System Configuration : BBS`). Options are numbered rows in the form:

```
1. board_name = RSMesh BBS
2. eventbus_topic = meshtastic.receive
...
0. Back to System Configuration
```

Select a row to edit that setting. The form shows the **Key** (read-only) and prompts for a new **Value**. Editors are type-aware where defined: **Y/N** for booleans, constrained choices for `interface.type`, numeric validation for schedule minutes, and format checks for node IDs and radio short names. Press Enter to keep the current value.

Under **Interface**, optional `node_id`, `short_name`, and `long_name` identify this BBS on the mesh. Leave them empty to use values from the connected radio when available. Modules can read these through the read-only BBS info API.

#### Export Configuration to config.yml

Writes the known `bbs`, `interface`, and `schedule` keys from `sys_config` back to `config.yml` in schema order. Confirmation:

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

**Line 3:** `Mail: {Y/N}  Mesh nodes: {Y/N}  Modules: {Y/N}  Last heard: {relative time}` (`Modules: Y` when rsv1 per-module sync flags are stored; `N` otherwise)

**Line 4 (optional, rsv1 only):** `Modules: {Name} out=N, {Name} in=N` — shown only when a module sync restriction is set for this peer (default allow omits the line).

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
| `{Module name} sync out (Y/N) [Y]:` | Y | **rsv1 only** — send module sync to this peer (one prompt per module that registers sync) |
| `{Module name} ingest in (Y/N) [Y]:` | Y | **rsv1 only** — accept module sync from this peer |
| `Enabled (Y/N) [Y]:` | Y | **Last prompt** — master on/off for this peer; **`N`** skips all outbound and inbound sync |

Module sync prompts appear only when the peer protocol is **`rsv1`** and at least one enabled module registers sync hooks. Answering those prompts stores per-peer module rows (including **`Y`/`Y`** allow-all); **`Modules: Y`** on list lines reflects stored rows. **`tc2`** peers show `Module sync: N/A (rsv1 only).`

**Protocol behavior:**
- **`tc2`** — TC²-compatible pipe-delimited sync (`BULLETIN|`, `MAIL|`, etc.). Maintains TC²-BBS-mesh conventions: bulletin sync is **create-only** (duplicate `unique_id` ingests are skipped; pin/edit updates are **not** sent). Mesh node sync is forced to **`N`**. Messages must fit in one 200-byte packet.
- **`rsv1`** — RS wire format (`RS|1|TYPE|{json}`). Supports bulletin **upsert** by `unique_id` (edits and **Pinned** changes propagate), chunked oversized payloads, mesh node sync, and RS version negotiation. See [Sync wire formats](RSMESH-BBS-DEVELOPER-GUIDE.md#sync-wire-formats) and [rsv1 message examples](RSMESH-BBS-DEVELOPER-GUIDE.md#rsv1-sync-message-examples).

Duplicate `bbs_node` values are rejected on add.

#### List Unsynced Data

Read-only report of records not yet synced to all eligible peers. Grouped into **Bulletins**, **Mail**, and **Channels** sections.

Each entry shows ID, key fields, sync status (`pending sync` or `pending delete sync` for deleted bulletins), and **Pending peers** (peer names or `all peers`).

**Modules** section lists module-owned records when an enabled module registers a `list_unsynced` hook and the record still has pending rsv1 peers. Each entry shows module name, record key, label, and pending peers.

### Modules

| Option | Action |
|--------|--------|
| `1` | List Modules |
| `2` | Edit Module Flags |
| `3` | Suppress Modules Submenu (On/Off) |
| `4+` | Dynamic entries for enabled modules with an admin screen |
| `0` | Back |

#### List Modules — per module (2 lines)

- `ID: {id}  Name: {name}  Menu: {menu_option}`
- `Dir: {dir}  Enabled: {Y/N}  Schedule: {Y/N}  Main Menu: {Y/N}`

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
| `Show on main menu (Y/N) [{current}]:` | Y/N — promote this module’s menu letter to the mesh main menu |

**Suppress Modules Submenu** toggles `bbs.suppress_modules_menu`. Use **on** to drop the redundant M[o]dules entry when every enabled module is already on the main menu. The toggle is rejected if any enabled module is not promoted — see [M[o]dules on the main menu](#modules-on-the-main-menu).

#### Module admin submenus

Enabled modules with `modules/{dir}/{dir}_admin.py` appear as additional numbered options. See [Module admin screens](#module-admin-screens) below and the [Developer Guide](RSMESH-BBS-DEVELOPER-GUIDE.md#modules) for module development.

### Backup

**Administration → Backup** creates a timestamped `backup/backup_YYYYMMDDHHMMSS.zip` with no further prompts. SQL dumps are written briefly under `backup/staging/` (same layout as the live tree), then removed after the zip is created.

The archive contains:
- SQL dumps of all `*.db` files in the project root and under `modules/*/` (for example `rsmesh-bbs.sql`, `modules/node_info/node_info.sql`)
- `config.yml` and all `modules/*/config.yml` files

Dumps use SQLite’s connection API, so WAL sidecar files are not required. Success message reports file count, SQL dump count, and config count.

Restore by unzipping and loading each `.sql` with `sqlite3 database.db < dump.sql`.

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

**Urgent alerts:** When `bbs.send_urgent_alert_local` is `true`, **Add Bulletin** to the Urgent board queues a mesh broadcast for the running server (not sent from the admin tool directly). **Edit Bulletin** never queues or sends an Urgent alert, including when the board is changed to Urgent. See README “Urgent board alerts” for `send_urgent_alert_local` and `send_urgent_alert_from_sync`.

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

When the board is **Urgent** and `bbs.send_urgent_alert_local` is `true`, the server queues a mesh broadcast alert (delivered by the running BBS process, not from the admin tool).

New bulletins are **not** pinned (`Pinned: N`). Use **Edit Bulletin** to pin or unpin.

### Edit Bulletin

Select: `Enter ID or X=cancel:`

Editable: Board, Poster short name, Subject, Pinned (Y/N). Optional content re-entry when `Edit content? (Y/N) [N]:` is **`Y`**. Saving resets sync status so **rsv1** peers receive the update. **tc2** peers keep the original bulletin only.

**Pinned (Y/N):** When `Y`, the bulletin stays on mesh board menus and read lists regardless of `schedule.bulletin_display_age_days`. Pinned posts are listed before unpinned posts on the mesh. When `N`, the bulletin is subject to the display-age limit like any normal post. Mesh users cannot change this flag; only the admin tool can. Pin changes sync to **rsv1** peers only. See README “Pinned bulletins”.

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

Optional **operator convenience** — a notebook of nodes you want on file. Distinct from **Mesh Nodes** (nodes observed on the air) and from the **Node Info** module database.

The BBS server uses catalog rows only for **short-name/hex ID lookup**, **mail inbox matching**, **BBS Mail Forward To**, and **BBS Admin** (sync to `sysadmin_nodes`). Fields such as `public_key`, `private_key`, `ble_pin`, `has_gps`, `hardware`, and `comment` are optional operator notes and are never read by server logic.

**Mesh admin (Y/N)** is an operator reference flag only — it does not change BBS or mesh behavior. Set **`Y`** when **this catalog entry is the administrator node** that will send remote config changes to other radios (not when this node is the one being administered). On each **target** radio, add **this node's public key** under **Radio Config → Security → Admin Settings** (Primary, Secondary, or Tertiary Admin Key). Configured targets will accept changes from the Mesh Admin node per Meshtastic specs; unconfigured nodes will not. The flag only documents that you have made (or intend to make) those radio-side settings. Use the catalog **Public key** field optionally to record the administrator node's key for your own fleet documentation.

See [Node catalog (operator reference)](#node-catalog-operator-reference) for the full runtime field matrix.

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

List **Admin: Y** when `mesh_admin=Y` or `bbs_admin=Y` (visual hint only for `mesh_admin`; only `bbs_admin` affects BBS permissions).

**Detail view fields:** ID, Short Name, Long Name, Node Hex Username, Mesh Admin, BBS Admin, BBS Mail Forward To, Has GPS, Public Key, Private Key, BLE PIN, Hardware, Comment, Created, Updated

### Add Node Catalog Entry

| Prompt | Default | Required |
|--------|---------|----------|
| `Long name:` | — | Yes |
| `Short name:` | — | Yes |
| `Node hex username (e.g. !9e9d8704):` | — | Yes |
| `Mesh admin (Y/N) [N]:` | N | Y/N — operator reference: this node is the remote **administrator** (its public key goes on other radios' Admin Settings) |
| `BBS admin (Y/N) [N]:` | N | Y/N — syncs `sysadmin_nodes` when `Y` |
| `BBS mail forward to (optional):` | — | No |
| `Has GPS (Y/N) [N]:` | N | Y/N |
| `Public key (optional):` | — | No |
| `Private key (optional):` | — | No |
| `BLE PIN [123456]:` | 123456 | No |
| `Hardware (optional):` | — | No |
| `Comment (optional):` | — | No |

Adding or changing `bbs_admin` syncs the `sysadmin_nodes` table.

**BBS mail forward to** — optional hex node ID or short name. When mail is addressed to this catalog entry, it is stored for the forward target instead, with a `Sent to {short name}` footer. See [Mail forwarding](#mail-forwarding).

### Edit / Delete Node Catalog Entry

Select: `Enter catalog ID or X=cancel:` (delete supports comma-separated IDs).

### Export / Import CSV

Default filename: `node_catalog.csv`

**CSV columns:** `long_name`, `short_name`, `node_hex_username`, `mesh_admin`, `bbs_admin`, `bbs_mail_forward_to`, `has_gps`, `public_key`, `private_key`, `ble_pin`, `hardware`, `comment`, `created`, `updated`

**Required on import:** `long_name`, `short_name`, `node_hex_username`

**Y/N columns:** `mesh_admin`, `bbs_admin`, `has_gps` (invalid values default to `N`)

Import mode: Replace (`R`) or Append (`A`, default).

---

## Mesh Nodes

Core **minimal node directory** in the main database (`mesh_nodes`): hex node ID, short name, long name, and last heard. The server populates it automatically from live mesh traffic and from **rsv1** peer sync when **Sync mesh nodes** is enabled. This store supports mail recipient lookup, short-name resolution, and mesh-node sync **without** requiring the optional **Node Info** module.

Operators can also add, edit, import, export, or purge rows here. See [Mesh nodes vs Node Info](#mesh-nodes-vs-node-info).

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

Optional module (disable under **Modules** if you do not want enhanced telemetry). Unlike **Mesh Nodes**, which holds minimal IDs/names for core server operation, Node Info maintains a separate database of richer overheard-packet telemetry (signal, GPS, hops, etc.) for operator reference and mesh user statistics.

| Option | Action |
|--------|--------|
| `1` | List Node Info |
| `0` | Back to Modules |

Data comes from `modules/node_info/node_info.db` (not the main BBS database). See [Mesh nodes vs Node Info](#mesh-nodes-vs-node-info).

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

| Protocol | Wire format | Bulletin updates | Pinned on wire | Mesh node sync |
|----------|-------------|------------------|----------------|----------------|
| `tc2` | Pipe-delimited (`BULLETIN|`, `MAIL|`, …) | Create-only (TC² standard) | No | Not supported |
| `rsv1` | `RS\|1\|TYPE\|{json}` | Upsert by `unique_id` | Yes (`pin`) | Supported when enabled per peer |

See [Sync wire formats](RSMESH-BBS-DEVELOPER-GUIDE.md#sync-wire-formats) and [rsv1 message examples](RSMESH-BBS-DEVELOPER-GUIDE.md#rsv1-sync-message-examples) for the full comparison.

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
    │   ├── 2. Core Services
    │   ├── 3. Regenerate Main Menu
    │   ├── 4. Sysadmin Nodes
    │   ├── 5. Sync Peers
    │   ├── 6. Modules
    │   │   ├── Suppress Modules Submenu
    │   │   ├── [Node Info] → List Node Info
    │   │   └── [Example Hello] → List Visits (if enabled)
    │   └── 7. Backup
    ├── 3–5. Bulletins / Channels / Mail (when core service enabled)
    ├── Node Catalog
    ├── Mesh Nodes
    └── 0. Exit
```

Mesh main menu (separate from the admin tool): title line plus cached `mesh_ui/main_menu.txt`. Default body: `[B]ulletins` / `[C]hannels`, `[M]ail` / M[o]dules (`O`), `E[X]IT`; mail submenu `[R]` / `[S]`. Optional **Display Mail commands on Main Menu** replaces `[M]ail` with `[R]` / `[S]` on the main menu. See [Mesh main menu (cached file)](#mesh-main-menu-cached-file) and the [User Guide](RSMESH-BBS-USER-GUIDE.md).
