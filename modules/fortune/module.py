from rsmesh_bbs.module_loader import MODULE_RESULT_CONTINUE, MODULE_RESULT_EXIT

from fortune import fortunes


class Module:
    def on_load(self, ctx):
        self._fortunes_path = ctx.path(fortunes.FORTUNES_FILE)

    def on_enter(self, sender_id, ctx):
        self._send_fortune(sender_id, ctx)

    def on_message(self, sender_id, message, ctx):
        message = message.lower().strip()
        if len(message) == 2 and message[1] == "x":
            message = message[0]
        if message == "x":
            return MODULE_RESULT_EXIT
        self._send_fortune(sender_id, ctx)
        return MODULE_RESULT_CONTINUE

    def _send_fortune(self, sender_id, ctx):
        lines = fortunes.load_fortunes(self._fortunes_path)
        fortune = fortunes.pick_fortune(lines)
        if fortune is None:
            ctx.send_user_message(sender_id, "No fortunes available.\nE[X]IT")
            return
        menu = (
            f"= {ctx.module_name} =\n"
            "Send any message for another fortune.\n"
            "E[X]IT"
        )
        ctx.send_user_messages(sender_id, [fortunes.decorate_fortune(fortune), menu])
