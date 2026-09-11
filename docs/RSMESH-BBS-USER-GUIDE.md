# RSMesh BBS User Guide

Release 1.1

How mesh users interact with the BBS from a Meshtastic handset (or the in-process [mesh client](RSMESH-BBS-SYSOP-GUIDE.md#mesh-client-no-radio)).

Send commands as **direct messages to the BBS node**. The server ignores group-channel traffic and messages addressed to other nodes. After connecting, send any letter command or an unrecognized message to open the main menu.

## Main menu

```
[B]ulletins  [C]hannels
[M]ail       M[o]dules
E[X]IT
```

| Key | Action |
|-----|--------|
| `B` | Bulletin boards |
| `C` | Channel directory (view published channels or post a new entry) |
| `M` | Mail submenu (when core mail is enabled) |
| `O` | Enabled modules (Fortune, Node Info, etc.) |
| `X` | Main menu (also `E[X]IT` prompts in submenus) |

**Mail submenu** (`M`):

```
= Mail =
[R]ead Mail  [S]end Mail
```

| Key | Action |
|-----|--------|
| `R` | Read mail |
| `S` | Send mail |
| `X` | Back to main menu |

When core mail is disabled in the admin tool, `[M]ail` is hidden from the main menu. `[B]ulletins` and `[C]hannels` stay visible so an enabled module can register the same menu letter for its own feature.

Some BBS systems run **optional modules** that extend core features (for example Fortune, Node Info, or custom operator-installed modules). Open **M[o]dules** (`O`) to see what is available on this node; module names, menu keys, and actions vary by system. See [Shipped modules](RSMESH-BBS-SYSOP-GUIDE.md#shipped-modules-mesh-menus) in the Sysop Guide for common examples.

Many submenus accept a two-letter exit shortcut (for example `Rx` runs **R** then returns to the main menu via **X**).

## Bulletins

Board menu: `[G]eneral` `[I]nfo` `[N]ews` `[U]rgent`

On a board: `[R]ead` `[P]ost`, and `[D]elete` for **sysadmin** nodes only. **Urgent** posting is also sysadmin-only.

- **Read** — pick a bulletin number from the list, then `X` to return to the board menu.
- **Post** — enter a short subject, then send the body across one or more messages; send `END` on its own line to finish.
- **Delete** (sysadmin) — pick a bulletin number to soft-delete.

See [Pinned bulletins](RSMESH-BBS-SYSOP-GUIDE.md#pinned-bulletins) and [Urgent board alerts](RSMESH-BBS-SYSOP-GUIDE.md#urgent-board-alerts) in the Sysop Guide for operator-controlled behavior.

## Mail

Open mail from the main menu with **`M`**, then **`R`** (read) or **`S`** (send).

**Read mail** — select a message number, then `[K]eep`, `[D]elete`, or `[R]eply`. Reply uses the same multiline `END` flow as posting. An empty inbox returns to the mail submenu.

**Send mail** — enter the recipient **short name** (or pick from a list when several nodes match). Subject, then body with `END` to finish. While you type the body, the BBS may send no reply until `END` (the mesh client hides those empty turns unless you pass `--verbose`). Recipient lookup uses nodes seen on the radio, the [mesh node directory](RSMESH-BBS-SYSOP-GUIDE.md#node-directory), the [node catalog](RSMESH-BBS-SYSOP-GUIDE.md#node-catalog-operator-reference), and the Node Info module when enabled.

## Channel directory

`[V]iew` — list published channels and show name/PSK for a selected entry.

`[P]ost` — submit a channel name and PSK for operator review. Mesh posts are stored unpublished until an operator sets **Publish** to `Y` in the admin tool (see [Channel directory](RSMESH-BBS-SYSOP-GUIDE.md#channel-directory) in the Sysop Guide).

## Sysadmin capabilities on the mesh

Sysadmin nodes (`sysadmin_nodes`, seeded from `bbs.superuser_node` and node catalog **BBS Admin**) can post to **Urgent**, delete bulletins on any board, and use extra module actions where documented (for example Node Info **List Nodes**).
