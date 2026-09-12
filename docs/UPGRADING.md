# Upgrading

Release 1.1

## Upgrading from TC²

RSMesh BBS can migrate a stock [TC²-BBS-Mesh](https://github.com/TheCommsChannel/TC2-BBS-mesh) install on first startup. Complete [Setup (virtual environment)](../README.md#setup-virtual-environment), place your existing TC² files in the project directory, and start the server with the venv activated:

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

## Upgrading from RSMesh BBS 1.0

Pull the 1.1 release, reinstall dependencies when `requirements.txt` changes, and restart the server (or admin tool / mesh client — all call the same upgrade path). On startup:

1. **`config.yml`** — missing 1.1 keys merged from `example_config.yml` (core services, mail layout, interface radio identity fields, schedule defaults)
2. **Database** — idempotent schema completion to 1.1 (for example `modules.main_menu_visible`, `sync_peer_modules`, and any columns or support tables added since your 1.0 install)
3. **`sys_config`** — required keys seeded from `config.yml` / `example_config.yml` (including `bbs.database_version`)
4. **Modules** — new default modules (for example BBS List) added without disturbing existing rows
5. **Main menu** — `mesh_ui/main_menu.txt` regenerated when an existing database is upgraded to 1.1

TC² and 1.0 upgrades share the same 1.1 schema completion step; TC² additionally imports `config.ini` / `bulletins.db` when those files are present. Review [changelog.txt](../changelog.txt) and the [Sysop Guide](RSMESH-BBS-SYSOP-GUIDE.md) for new operator features.
