import time

from rsmesh_bbs.module_loader import MODULE_RESULT_CONTINUE, MODULE_RESULT_EXIT
from node_info import storage


class Module:
    def on_load(self, ctx):
        storage.configure(ctx.module_dir)
        purge_minutes = max(1, storage.PURGE_SECONDS // 60)
        ctx.register_service("node_directory", storage.NodeDirectory())
        ctx.register_schedule("scan", 1, self._scan)
        ctx.register_schedule("purge", purge_minutes, self._purge)

    def on_enter(self, sender_id, ctx):
        ctx.send_user_message(sender_id, self._menu_text(ctx, sender_id))

    def on_message(self, sender_id, message, ctx):
        message = message.lower().strip()
        if len(message) == 2 and message[1] == "x":
            message = message[0]
        if message == "x":
            return MODULE_RESULT_EXIT

        menu = self._menu_text(ctx, sender_id)
        if message == "n":
            ctx.send_user_messages(sender_id, [self._node_counts_text(ctx), menu])
        elif message == "h":
            ctx.send_user_messages(sender_id, [self._hardware_counts_text(ctx), menu])
        elif message == "r":
            ctx.send_user_messages(sender_id, [self._role_counts_text(ctx), menu])
        elif message == "l":
            if not ctx.is_sysadmin(sender_id):
                ctx.send_user_messages(
                    sender_id,
                    ["You do not have permission to list nodes.", menu],
                )
            else:
                ctx.send_bundled(
                    sender_id,
                    ["= Node List ="] + storage.format_mesh_node_list_lines(),
                    trailing_message=menu,
                )
        else:
            ctx.send_user_messages(sender_id, ["Invalid selection.", menu])
        return MODULE_RESULT_CONTINUE

    def _scan(self, ctx):
        if ctx.interface is not None:
            storage.scan_mesh_nodes(ctx.interface)

    def _purge(self, ctx):
        storage.purge_old_nodes()

    def _menu_text(self, ctx, sender_id):
        actions = "[N]odes  [H]ardware  [R]oles"
        if ctx.is_sysadmin(sender_id):
            actions += "  [L]ist Nodes"
        return f"= {ctx.module_name} =\nSelect:\n{actions}\nE[X]IT"

    def _node_counts_text(self, ctx):
        current_time = int(time.time())
        timeframes = {
            "All time": None,
            "Last 24 hours": 86400,
            "Last 8 hours": 28800,
            "Last hour": 3600,
        }
        summary = []
        for period, seconds in timeframes.items():
            if seconds is None:
                total_nodes = len(ctx.interface.nodes)
            else:
                time_limit = current_time - seconds
                total_nodes = sum(
                    1 for node in ctx.interface.nodes.values()
                    if node.get("lastHeard") is not None and node["lastHeard"] >= time_limit
                )
            summary.append(f"- {period}: {total_nodes}")
        return "Total nodes seen:\n" + "\n".join(summary)

    def _hardware_counts_text(self, ctx):
        hw_models = {}
        for node in ctx.interface.nodes.values():
            hw_model = node["user"].get("hwModel", "Unknown")
            hw_models[hw_model] = hw_models.get(hw_model, 0) + 1
        return "Hardware Models:\n" + "\n".join(
            f"{model}: {count}" for model, count in hw_models.items()
        )

    def _role_counts_text(self, ctx):
        roles = {}
        for node in ctx.interface.nodes.values():
            role = node["user"].get("role", "Unknown")
            roles[role] = roles.get(role, 0) + 1
        return "Roles:\n" + "\n".join(f"{role}: {count}" for role, count in roles.items())
