# RSMesh BBS 1.1 — QA Process

Release target: **1.1**  
Document purpose: operator checklist for full regression testing before release sign-off.  

**Phases:** 1 Install/upgrade → 2 User mesh → 3 Sysadmin + admin → 4 rsv1 peer setup → 5 rsv1 sync → **6 RSMesh ↔ TC² interop**

Companion docs: [UPGRADING.md](UPGRADING.md), [RSMESH-BBS-SYSOP-GUIDE.md](RSMESH-BBS-SYSOP-GUIDE.md), [RSMESH-BBS-USER-GUIDE.md](RSMESH-BBS-USER-GUIDE.md)

---

## Test environment

| Item | Machine A | Machine B |
|------|-----------|-----------|
| Host name / label | | |
| Meshtastic node ID | | |
| Short name | | |
| Board name (`bbs.board_name`) | | |
| Install path | | |
| Branch tested (record per phase) | | |
| Radio connection (`serial` / `tcp`) | | |
| Phase 6 role | RSMesh **1.1** | Stock **TC²-BBS** |

**Mesh client identities** (for Phases 2–3; `config_client.yml` per workstation):

| Role | Node ID | Short name | Sysadmin? |
|------|---------|------------|-----------|
| Regular user | | | No |
| Sysadmin user | | | Yes |

**Notes (environment setup):**

```

```

---

## Conventions

- `[ ]` = not tested / failed — leave unchecked until pass
- Record failures inline under **Notes**; include date, branch, and log snippet if helpful
- **Admin** = `rsmesh-bbs_admin.py`
- **Client** = `rsmesh-bbs_client.py --fast` (add `-v` when debugging silent paths)
- **Server** = `rsmesh-bbs_server.py` with venv activated
- After admin changes to sync peers or sysadmin nodes, confirm the running server picks them up (next mesh message or worker cycle)

---

## Phase 1 — Install and upgrade paths

Goal: validate TC² migration, 1.0 → 1.1 upgrade, and fresh TC² → 1.1 on two independent systems.

### 1.1 Baseline — reinstall TC² on both machines

- [ ] Remove or archive prior RSMesh install (keep backup if needed)
- [ ] Install stock [TC²-BBS-Mesh](https://github.com/TheCommsChannel/TC2-BBS-mesh) on **Machine A**
- [ ] Install stock TC² on **Machine B**
- [ ] Confirm each TC² server starts and accepts mesh/client traffic
- [ ] Seed distinctive test data on each (at least one bulletin, one mail message, one channel if supported)

**Notes:**

```

```

### 1.2 Upgrade Machine A to release 1.0

- [ ] Clone/checkout `1.0` branch; create venv; `pip install -r requirements.txt`
- [ ] Place existing TC² `config.ini` and `bulletins.db` in project directory
- [ ] Start server; confirm migration messages (`config.ini` → `config.yml`, `bulletins.db` → `rsmesh-bbs.db`)
- [ ] Verify migrated bulletins and config values
- [ ] Confirm `[sync] bbs_nodes` imported to `sync_peers` with **all sync flags N** (sync disabled until admin enables)
- [ ] Confirm `[allow_list]` imported to `sysadmin_nodes` where applicable
- [ ] Smoke-test server starts cleanly after restart

**Notes:**

```

```

### 1.3 Upgrade both machines to release 1.1

**Machine A (from 1.0):**

- [ ] Pull/checkout `1.1`; reinstall dependencies if `requirements.txt` changed
- [ ] Start server; confirm 1.1 schema/sys_config seeding (no data loss)
- [ ] Confirm new default modules appear (Node Info, Fortune, BBS List, Example Hello row)
- [ ] Confirm `mesh_ui/main_menu.txt` regenerated or valid
- [ ] Confirm `admin.server_log_file` seeded (`rsmesh-bbs.log`); log file created on server start
- [ ] Review [changelog.txt](../changelog.txt) items relevant to upgrade

**Machine B (TC² → 1.1 direct):**

- [ ] Fresh `1.1` install over TC² files (no prior RSMesh DB)
- [ ] Confirm TC² migration path same as UPGRADING.md
- [ ] Confirm 1.1-only features present (core services, module sync tables, etc.)
- [ ] Smoke-test server starts cleanly after restart

**Notes:**

```

```

### 1.4 Phase 1 exit criteria

- [ ] Both machines run **1.1** server without errors
- [ ] Admin tool opens on both; splash shows expected counts
- [ ] **System Status → [V]iew server log** works (Ctrl-C returns); log shows startup lines
- [ ] No unintended overwrite of pre-existing `config.yml` / `rsmesh-bbs.db` on re-run

**Notes:**

```

```

---

## Phase 2 — Mesh client testing (regular user)

Goal: exercise every core service and shipped module menu path as a **non-sysadmin** handset. Use **Client** with the regular-user identity.

**Preparation:**

- [ ] Enable all core services: **Admin → Core Services** (Bulletins, Mail, Channels = Enabled)
- [ ] Enable shipped modules: Node Info, Fortune, BBS List (Example Hello optional)
- [ ] Confirm main menu shows `[B]`, `[C]`, `[M]`, M[o]dules (`O`), `E[X]IT`
- [ ] Do **not** grant sysadmin to the test client node yet

### 2.1 Main menu and help

- [ ] Send any message to open main menu
- [ ] Confirm menu matches `mesh_ui/main_menu.txt` / board name banner
- [ ] `X` or invalid key behavior acceptable
- [ ] `?` / help if applicable

**Notes:**

```

```

### 2.2 Bulletins (user)

- [ ] `B` → board menu: General, Info, News, Urgent visible
- [ ] `G` / `I` / `N` → Read: list, open bulletin, `X` back
- [ ] Post to **General**: subject + multi-line body, `END` terminator
- [ ] Post to **Info** and **News**
- [ ] **Urgent**: confirm regular user **denied** (sysadmin required)
- [ ] Confirm **no** `[D]elete` option for regular user
- [ ] Pinned vs aged bulletin display (if test data spans `bulletin_display_age_days`)

**Admin visibility (no action yet — observe later):**

- [ ] New posts appear in **Admin → Bulletins → List**

**Notes:**

```

```

### 2.3 Mail (user)

- [ ] `M` → `R` Read: empty inbox message vs populated inbox
- [ ] Read message: `K` keep, `D` delete own mail, `R` reply flow
- [ ] `M` → `S` Send: recipient by short name; multi-line body + `END`
- [ ] Send to peer short name (second client identity on other machine optional in Phase 2)
- [ ] Empty inbox returns to mail submenu (not main menu)

**Admin visibility:**

- [ ] Sent/received mail in **Admin → Mail → List**

**Notes:**

```

```

### 2.4 Channels (user)

- [ ] `C` → View (`V`): list published channels only
- [ ] View detail: name + PSK shown
- [ ] Post (`P`): submit name + PSK for operator review
- [ ] Confirm posted channel **not** visible in mesh View until published

**Admin visibility (Phase 3):**

- [ ] Unpublished channel in **Admin → Channels → List** (`publish=N`)

**Notes:**

```

```

### 2.5 Modules — Fortune (`F`)

- [ ] `O` → `F`: fortune displayed on entry
- [ ] Any message fetches another fortune
- [ ] `X` exits to modules or main menu

**Notes:**

```

```

### 2.6 Modules — Node Info (`I`)

- [ ] `O` → `I`: `[N]odes` counts by time window
- [ ] `[H]ardware` model counts
- [ ] `[R]oles` role counts
- [ ] Confirm **no** `[L]ist Nodes` (sysadmin only)
- [ ] `X` exits

**Notes:**

```

```

### 2.7 Modules — BBS List (`L`)

- [ ] `O` → `L`: All boards list (`A` if needed)
- [ ] `[S]ync` list shows sync-interested only; `*` marker on interested rows
- [ ] Enter **list ID** → detail view
- [ ] `?` help, `X` exit

**Notes:**

```

```

### 2.8 Optional — Example Hello (if enabled)

- [ ] Enable in **Admin → Modules** temporarily
- [ ] Mesh entry greets; visit recorded
- [ ] Disable again if not part of release scope

**Notes:**

```

```

### 2.9 Core Services toggles (mesh menu visibility)

Repeat a subset after each toggle; restore all enabled at end.

- [ ] Disable **Mail** → `[M]ail` hidden on mesh main menu; re-enable
- [ ] Disable **Bulletins** → `[B]ulletins` hidden; re-enable
- [ ] Disable **Channels** → `[C]hannels` hidden; re-enable
- [ ] Toggle **Display Mail commands on Main Menu** → `[R]`/`[S]` on main menu vs `[M]` submenu

**Notes:**

```

```

### 2.10 Phase 2 exit criteria

- [ ] All checked paths work without server traceback in `rsmesh-bbs.log`
- [ ] User guide behavior matches observation ([RSMESH-BBS-USER-GUIDE.md](RSMESH-BBS-USER-GUIDE.md))

**Notes:**

```

```

---

## Phase 3 — Sysadmin mesh + admin tool

Goal: grant sysadmin; test elevated mesh actions and every admin screen needed for **approval, visibility, and configuration**.

### 3.1 Grant sysadmin

- [ ] **Admin → Sysadmin Nodes → Add** regular-user node (Phase 2 client)
- [ ] Optionally set `bbs.superuser_node` in **System Configuration → BBS** if testing Urgent + superuser combo
- [ ] Restart client; confirm sysadmin menus appear on mesh

**Notes:**

```

```

### 3.2 Bulletins (sysadmin mesh)

- [ ] Post to **Urgent** board succeeds
- [ ] `[D]elete` on board → select bulletin → soft-delete
- [ ] If `send_urgent_alert_local=true`: urgent post triggers primary-channel alert (or queued for server)

**Admin follow-up:**

- [ ] **List Bulletins** shows deleted flag / sync label
- [ ] **Edit Bulletin**: pin/unpin; confirm sync label changes to pending (rsv1)
- [ ] **Delete Bulletins** (admin) soft-deletes
- [ ] **Review Reconcile Bulletins** (after Phase 5 delete sync) — defer if empty

**Notes:**

```

```

### 3.3 Channels (admin approval)

- [ ] Approve user-posted channel: **Edit Channel** → `publish=Y`
- [ ] Mesh View now shows channel
- [ ] **Add Channel** directly with publish Y/N
- [ ] **Delete Channels** / **Export / Import CSV** smoke test
- [ ] **Review Reconcile Channels** when applicable

**Notes:**

```

```

### 3.4 Mail (admin)

- [ ] **List / Send / Edit / Delete** mail
- [ ] Forwarding test if `mail_forward_to` configured in node catalog

**Notes:**

```

```

### 3.5 Node Catalog and Mesh Nodes (admin)

- [ ] **Node Catalog**: add, edit, delete, export/import CSV
- [ ] Confirm `bbs_admin=Y` on catalog row syncs sysadmin when applicable
- [ ] **Mesh Nodes**: list, add, edit, delete, purge, export/import CSV

**Notes:**

```

```

### 3.6 Modules (admin)

- [ ] **List Modules** — flags match expected defaults
- [ ] **Edit Module Flags**: enable/disable, schedule, **Show on main menu**
- [ ] **Suppress Modules Submenu** (only when all enabled modules promoted)
- [ ] **Regenerate Main Menu** after hand-editing `mesh_ui/main_menu.txt`
- [ ] **Node Info → List Node Info** (view-only)
- [ ] **BBS List admin**: Register This BBS, Add, Edit (paginated ID pick), Delete, List Sync Interested

**Notes:**

```

```

### 3.7 System Configuration and Core Services

- [ ] **System Configuration**: edit BBS, Interface, Schedule keys (type-aware editors)
- [ ] **Export Configuration to config.yml** (confirm overwrite prompt)
- [ ] **Core Services**: toggle each service; leave all **Enabled** before Phase 4
- [ ] **Backup** creates zip under `backup/`

**Notes:**

```

```

### 3.8 System Status and logging

- [ ] **System Status** counts match splash / database
- [ ] Sync peer list shown when configured (Phase 4)
- [ ] **[V]iew server log (Ctrl-C to return)** tails `rsmesh-bbs.log`
- [ ] Sync alert summary line (RS version / module peers) when applicable

**Notes:**

```

```

### 3.9 Phase 3 exit criteria

- [ ] Sysadmin mesh capabilities match user guide
- [ ] All admin menus navigable; no crashes
- [ ] Channel approval workflow complete (mesh post → admin publish → mesh view)

**Notes:**

```

```

---

## Phase 4 — Sync peer configuration

Goal: pair Machine A and Machine B as **rsv1** peers with all sync options enabled. Complete on **both** machines.

### 4.1 Peer definitions

On **Machine A**, add peer = Machine B:

- [ ] **Admin → Sync Peers → Add**
- [ ] BBS node ID = Machine B node
- [ ] Protocol = **rsv1**
- [ ] Enabled = **Y**
- [ ] Out: bulletins **Y**, channels **Y**, mail **Y**, mesh nodes **Y**
- [ ] In: bulletins **Y**, channels **Y**
- [ ] Per-module: **BBS List** sync out **Y**, ingest in **Y** (and any other registered sync modules)
- [ ] Repeat mirror config on **Machine B** → Machine A

**Notes:**

```

```

### 4.2 Pre-sync verification

- [ ] **List Sync Peers** — four lines per peer; `Modules: Y` on line 3 for rsv1
- [ ] **List Unsynced Data** — baseline snapshot (existing local records may show pending)
- [ ] Clear stale module sync state if re-testing BBS List:  
  `DELETE FROM record_sync_peers WHERE record_type = 'module:bbs_list';` (both sides, only if needed)
- [ ] Server running on both; radios reach each other
- [ ] Note `peer_sync_minutes` (default 5) and mesh node delay (~90s after other sync)

**Notes:**

```

```

### 4.3 Phase 4 exit criteria

- [ ] Both peers listed, enabled, rsv1, all flags Y
- [ ] Server logs show sync worker started on both

**Notes:**

```

```

---

## Phase 5 — Sync testing (core + modules)

Goal: verify bidirectional sync, deletes, reconcile, and module wire types. Monitor **server logs** on both sides during tests.

### 5.1 Bulletins (rsv1)

**A → B:**

- [ ] Post bulletin on A; within sync cycle appears on B (mesh or admin list)
- [ ] **Edit** bulletin on A (subject or **Pinned**); update appears on B (rsv1 upsert)
- [ ] Admin **List Bulletins** sync label → `Y` when complete

**B → A:**

- [ ] Repeat reverse direction

**Delete + reconcile:**

- [ ] Delete bulletin on A (mesh sysadmin or admin); after purge cycle B marks reconcile
- [ ] **Admin → Review Reconcile Bulletins** on B: restore or confirm delete
- [ ] **List Unsynced Data** empty for that record when fully synced

**Notes:**

```

```

### 5.2 Mail

- [ ] Send mail A → B; appears in B inbox (mesh + admin)
- [ ] Send mail B → A
- [ ] Delete mail on one side; delete sync received on peer
- [ ] Sync labels on admin mail list

**Notes:**

```

```

### 5.3 Channels

- [ ] Publish channel on A; ingests on B as **unpublished** (`publish=N`)
- [ ] Admin publish on B; visible on B mesh
- [ ] Delete channel on A; reconcile on B
- [ ] **Review Reconcile Channels** workflow

**Notes:**

```

```

### 5.4 Mesh nodes (NODES batch, deferred)

- [ ] Ensure nodes heard on each system (live traffic or manual mesh node rows)
- [ ] Wait full cycle: core/module sync first, log line `Waiting 90 seconds before mesh nodes sync`, then `Mesh nodes sync to ... N batch(es)`
- [ ] Peer receives **NODES** ingest; **Admin → Mesh Nodes** updated
- [ ] Duplicate node IDs dedupe (newest `last_heard` wins) if testable

**Notes:**

```

```

### 5.5 BBS List module sync

- [ ] **Register This BBS** on A and B (local entries)
- [ ] Server log: `Sent BBS_LIST_SYNC` on sender; `Received message` + `Processing BBS_LIST_SYNC` + `Ingested` on receiver
- [ ] Mesh **BBS List** on peer shows remote board
- [ ] Edit local entry on A; re-syncs to B
- [ ] Inbound echo of own local entry does **not** mark peer synced incorrectly (no stuck “already synced”)
- [ ] **List Unsynced Data → Modules** section when pending
- [ ] Module sync restrictions: set BBS List out=N on one peer; confirm no send

**Notes:**

```

```

### 5.6 Sync health and edge cases

- [ ] **List Sync Peers** RS version alert if wire mismatch simulated (optional)
- [ ] Disable peer **Enabled=N**; confirm sync pauses; re-enable resumes
- [ ] Disable core service (e.g. Mail); confirm mail sync skipped inbound/outbound
- [ ] Urgent ingest: with `send_urgent_alert_from_sync=true`, urgent from peer triggers alert (optional)

**Notes:**

```

```

### 5.7 Phase 5 exit criteria

- [ ] All enabled record types sync bidirectionally
- [ ] Deletes and reconcile paths verified
- [ ] BBS List module sync reliable across restarts
- [ ] No unexplained gaps in server logs for send without receive
- [ ] **List Unsynced Data** accurate after steady-state

**Notes:**

```

```

---

## Phase 6 — RSMesh 1.1 ↔ TC² interop

Goal: verify **tc2** pipe-delimited sync between **RSMesh 1.1** (Machine A) and a stock **TC²-BBS** peer (Machine B). This is the expected production pattern — operators are not expected to run tc2 between two RSMesh nodes.

Run after Phase 5, or on a dedicated TC² install of Machine B while Machine A keeps its 1.1 peer list.

**tc2 expectations on the RSMesh side:**

| Feature | TC² peer |
|---------|----------|
| Wire format | `BULLETIN\|`, `MAIL\|`, `CHANNEL\|`, `DELETE_*` (single 200-byte packet) |
| Bulletins | **Create-only** by `unique_id` — edits and pin changes do **not** propagate |
| Channels | Ingest always **unpublished** on RSMesh; operator must publish locally |
| Mail | Bidirectional create/delete sync |
| Mesh nodes | **Not supported** (forced **N** on tc2 peer) |
| Module sync (BBS List, etc.) | **Not supported** (`Module sync: N/A`) |

**Topology:**

| Machine | Software | Phase 6 role |
|---------|----------|--------------|
| **A** | RSMesh **1.1** | tc2 sync peer → TC² node |
| **B** | Stock **TC²-BBS** | tc2 sync peer → RSMesh node |

**Notes:**

```

```

### 6.1 Peer setup (both sides)

**RSMesh (Machine A):**

- [ ] Complete Phase 5 first **or** add a **second** sync peer row for TC² (leave rsv1 peer intact if reusing hardware)
- [ ] **Admin → Sync Peers → Add** (or Edit if replacing test peer)
- [ ] BBS node = TC² node ID; protocol = **tc2**
- [ ] Enabled = **Y**; bulletins/mail/channels in/out = **Y** as needed
- [ ] Confirm **Mesh nodes: N** and **Module sync: N/A (rsv1 only)**
- [ ] **List Sync Peers** — protocol `tc2`, no module restriction line

**TC² (Machine B):**

- [ ] `config.ini` → `[sync]` `bbs_nodes` includes RSMesh node ID
- [ ] Enable sync flags per TC² documentation (bulletins, mail, channels)
- [ ] Restart TC² server; confirm it sees RSMesh as sync peer
- [ ] Note TC² sync interval / behavior for timing expectations

**Notes:**

```

```

### 6.2 Bulletins — create-only (tc2)

Use a **new** bulletin with a known `unique_id` (RSMesh admin list shows UID).

**RSMesh → TC²:**

- [ ] Post bulletin on RSMesh (mesh or admin); appears on TC² within sync cycle
- [ ] RSMesh log: outbound pipe `BULLETIN|` (not `RS|1|BULLETIN`)
- [ ] **Edit** or **pin** bulletin on RSMesh; wait sync cycle
- [ ] Confirm TC² still shows **original** content (create-only — no upsert)

**TC² → RSMesh:**

- [ ] Post bulletin on TC²; ingests on RSMesh (admin **List Bulletins** or mesh read)
- [ ] RSMesh log: pipe ingest (not RS decoder)
- [ ] Edit on TC² (if supported); confirm RSMesh copy unchanged

**Duplicate ingest:**

- [ ] Re-send same `unique_id`; RSMesh does not duplicate row

**Notes:**

```

```

### 6.3 Bulletins — delete and reconcile

**RSMesh deletes → TC²:**

- [ ] Soft-delete bulletin on RSMesh; `DELETE_BULLETIN|` reaches TC²
- [ ] Verify TC² handling (reconcile or remove per TC² behavior)

**TC² deletes → RSMesh:**

- [ ] Delete bulletin on TC²; RSMesh marks **delete_reconcile=Y**
- [ ] **Admin → Review Reconcile Bulletins** on RSMesh: **Restore**, then **Confirm delete**

**Notes:**

```

```

### 6.4 Mail (tc2)

- [ ] Send mail RSMesh → TC²; appears on TC² (mesh or TC² admin)
- [ ] Send mail TC² → RSMesh; appears in RSMesh inbox (mesh + admin)
- [ ] Delete mail on RSMesh; TC² copy removed (or note TC² behavior)
- [ ] Delete mail on TC²; RSMesh copy removed
- [ ] Keep bodies short (tc2 single-packet 200-byte limit); note failures on long content

**Notes:**

```

```

### 6.5 Channels (tc2)

- [ ] Publish channel on RSMesh (`publish=Y`); ingests on TC² per TC² rules
- [ ] Post/publish channel on TC²; ingests on RSMesh with **publish=N**
- [ ] RSMesh mesh **View** does not show channel until RSMesh admin sets `publish=Y`
- [ ] Delete channel on one side; reconcile or delete behavior on the other

**Notes:**

```

```

### 6.6 RSMesh-only features (must not sync to TC²)

- [ ] **No** mesh-node rows added on RSMesh from TC² peer traffic
- [ ] **No** `BBS_LIST_SYNC` or other module wire traffic to TC² peer
- [ ] **List Unsynced Data** on RSMesh — no **Modules** section pending for TC² peer
- [ ] BBS List **Register This BBS** on RSMesh does not appear on TC²
- [ ] RSMesh does **not** send `RS|1|…` wire to tc2 peer (logs show pipes only)

**Notes:**

```

```

### 6.7 Phase 6 exit criteria

- [ ] Bulletin **create** syncs both directions; **edit/pin do not** cross the link
- [ ] Delete + reconcile (or TC²-equivalent) verified for bulletins
- [ ] Mail send and delete work both directions within packet limits
- [ ] Channel ingest/publish rules correct on RSMesh side
- [ ] No RSMesh module or mesh-node leakage to TC² peer
- [ ] No errors/tracebacks in `rsmesh-bbs.log` during tc2 cycles
- [ ] Document any TC²-side quirks or timing differences for the sysop guide

**Notes:**

```

```

---

## Release sign-off

| Area | Tester | Date | Pass? |
|------|--------|------|-------|
| Phase 1 — Upgrade | | | |
| Phase 2 — User mesh | | | |
| Phase 3 — Sysadmin + admin | | | |
| Phase 4 — Peer setup | | | |
| Phase 5 — rsv1 sync | | | |
| Phase 6 — RSMesh ↔ TC² | | | |

**Open issues / doc updates needed:**

```

```

**Approved for 1.1 release:** _______________  **Date:** _______________

---

## Quick reference — admin actions triggered by mesh testing

| Mesh / user action | Admin screen to verify |
|--------------------|-------------------------|
| User posts channel | Channels → List (`publish=N`) |
| User posts bulletin | Bulletins → List |
| User sends mail | Mail → List |
| Sysadmin deletes bulletin | Bulletins → List (`Del: Y`); later reconcile on peer |
| Register BBS List entry | Modules → BBS List → List |
| Sync pending | Sync Peers → List Unsynced Data |
| Module sync pending | List Unsynced Data → Modules section |
| Peer delete bulletin/channel | Review Reconcile on receiving system |
| Urgent admin add | Server log / radio alert (not admin-sent) |
| TC² peer on RSMesh | List Sync Peers: protocol `tc2`, mesh nodes N, no module sync |
| RSMesh bulletin edit toward TC² | TC² copy unchanged (create-only) |
| TC² channel → RSMesh | Channels → List `publish=N` until RSMesh operator publishes |

---

*After QA is complete, update [RSMESH-BBS-SYSOP-GUIDE.md](RSMESH-BBS-SYSOP-GUIDE.md) and other operator docs with any corrections found during testing.*
