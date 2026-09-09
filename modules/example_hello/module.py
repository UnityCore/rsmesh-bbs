from rsmesh_bbs.module_loader import MODULE_RESULT_CONTINUE, MODULE_RESULT_EXIT
from example_hello import storage
from rsmesh_bbs.utils import get_node_id_from_num, get_node_short_name


class Module:
    def on_load(self, ctx):
        storage.configure(ctx.module_dir)
        ctx.register_schedule("greet_and_trim", storage.SCHEDULE_MINUTES, self._run_schedule)

    def on_enter(self, sender_id, ctx):
        short_name = self._sender_short_name(sender_id, ctx)
        storage.record_visit(sender_id, short_name)
        ctx.send_user_message(
            sender_id,
            f"= {ctx.module_name} =\n"
            f"Visit recorded for {short_name}.\n"
            f"A greeting will be sent on the next schedule run "
            f"(about {storage.SCHEDULE_MINUTES} min).\n"
            "E[X]IT",
        )

    def on_message(self, sender_id, message, ctx):
        message = message.lower().strip()
        if len(message) == 2 and message[1] == "x":
            message = message[0]
        if message == "x":
            return MODULE_RESULT_EXIT
        ctx.send_user_message(sender_id, "Nothing to do here. E[X]IT to return.")
        return MODULE_RESULT_CONTINUE

    def _run_schedule(self, ctx):
        pending = storage.get_pending_greetings()
        sent_ids = []
        for visit_id, sender_id, short_name in pending:
            ctx.enqueue_send(sender_id, f"Hello {short_name}!")
            sent_ids.append(visit_id)
        storage.mark_greetings_sent(sent_ids)
        storage.trim_visits()

    @staticmethod
    def _sender_short_name(sender_id, ctx):
        node_id = get_node_id_from_num(sender_id, ctx.interface)
        short_name = get_node_short_name(node_id, ctx.interface) if node_id else None
        return short_name or f"Node {sender_id}"
