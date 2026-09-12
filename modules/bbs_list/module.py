from rsmesh_bbs.module_loader import MODULE_RESULT_CONTINUE, MODULE_RESULT_EXIT
from rsmesh_bbs.module_sync import (
    ModuleSyncRegistration,
    get_pending_sync_peers,
    mark_sync_peers_synced,
    reset_record_sync_peers,
)
from rsmesh_bbs.sync_wire import build_rs_message
from rsmesh_bbs.utils import (
    get_sync_peer_by_bbs_node,
    send_sync_message,
    sync_peer_bbs_node,
    sync_peer_protocol,
)

from bbs_list import storage


class Module:
    def on_load(self, ctx):
        storage.configure(ctx.module_dir)
        ctx.register_sync(
            ModuleSyncRegistration(
                module_id=ctx.id,
                record_type=storage.RECORD_TYPE,
                wire_suffixes=(storage.WIRE_SUFFIX,),
                on_inbound_rs=self._ingest_bbs_list_rs,
                sync_pending=self._sync_pending_bbs_list,
                list_unsynced=storage.list_unsynced_items,
            )
        )

    def on_enter(self, sender_id, ctx):
        self._show_list(sender_id, ctx, sync_only=False)

    def on_message(self, sender_id, message, ctx):
        text = (message or "").strip()
        lowered = text.lower()
        if len(lowered) == 2 and lowered[1] == "x":
            lowered = lowered[0]
        if lowered == "x":
            return MODULE_RESULT_EXIT
        if lowered == "a":
            self._show_list(sender_id, ctx, sync_only=False)
            return MODULE_RESULT_CONTINUE
        if lowered == "s":
            self._show_list(sender_id, ctx, sync_only=True)
            return MODULE_RESULT_CONTINUE
        if lowered == "?":
            self._send_help(sender_id, ctx)
            return MODULE_RESULT_CONTINUE

        entry = storage.get_entry(text)
        if entry is None and not text.startswith("!"):
            entry = storage.get_entry("!" + text)
        if entry is not None:
            ctx.send_user_message(
                sender_id,
                f"= {ctx.module_name} =\n"
                f"{storage.format_mesh_detail(entry)}\n"
                "[A]ll  [S]ync  [?]Help  E[X]IT",
            )
            return MODULE_RESULT_CONTINUE

        ctx.send_user_message(
            sender_id,
            "Enter a node ID to view details, or A/S/?/X.\n"
            "[A]ll  [S]ync  [?]Help  E[X]IT",
        )
        return MODULE_RESULT_CONTINUE

    def _show_list(self, sender_id, ctx, sync_only=False):
        entries = storage.list_entries(sync_only=sync_only)
        title = "Sync-interested boards" if sync_only else "Known boards"
        if not entries:
            ctx.send_user_message(
                sender_id,
                f"= {ctx.module_name} =\n"
                f"No {title.lower()}.\n"
                "[A]ll  [S]ync  [?]Help  E[X]IT",
            )
            return

        header = (
            f"= {ctx.module_name} =\n"
            f"{title} ({len(entries)}). * = sync interest\n"
            "Enter node ID for details."
        )
        body_lines = [storage.format_mesh_list_line(entry) for entry in entries]
        footer = "[A]ll  [S]ync  [?]Help  E[X]IT"
        from rsmesh_bbs.utils import bundle_lines_for_mesh

        messages = bundle_lines_for_mesh([header] + body_lines + [footer])
        ctx.send_user_messages(sender_id, messages)

    def _send_help(self, sender_id, ctx):
        ctx.send_user_message(
            sender_id,
            f"= {ctx.module_name} =\n"
            "Directory of mesh BBS boards.\n"
            "* marks boards interested in sync.\n"
            "[A]ll list  [S]ync list  node ID view\n"
            "E[X]IT return to main menu",
        )

    def _ingest_bbs_list_rs(self, msg_type, fields, sender_node_id, interface):
        if not storage.upsert_from_wire(fields):
            return
        node_hex = storage.normalize_node_hex(fields.get("uid"))
        peer = get_sync_peer_by_bbs_node(
            sender_node_id,
            getattr(interface, "sync_peers", None),
        )
        if node_hex and peer:
            mark_sync_peers_synced(storage.RECORD_TYPE, node_hex, [peer])

    def _sync_pending_bbs_list(self, peers, interface):
        for entry in storage.list_entries():
            record_key = entry["node_hex"]
            pending = get_pending_sync_peers(
                storage.RECORD_TYPE,
                record_key,
                peers,
                interface,
            )
            if not pending:
                continue
            message = build_rs_message(1, storage.wire_type(), storage.entry_to_wire(entry))
            synced = []
            for peer in pending:
                if send_sync_message(
                    message,
                    sync_peer_bbs_node(peer),
                    interface,
                    sync_peer_protocol(peer),
                ):
                    synced.append(peer)
            if synced:
                mark_sync_peers_synced(storage.RECORD_TYPE, record_key, synced)


def queue_entry_sync(node_hex):
    node_hex = storage.normalize_node_hex(node_hex)
    if node_hex:
        reset_record_sync_peers(storage.RECORD_TYPE, node_hex)
