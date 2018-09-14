import channel_util
import slack_util


def list_hooks_callback_gen(hooks):
    # noinspection PyUnusedLocal
    def callback(slack, msg, match):
        slack_util.reply(slack, msg, "\n".join(hook.pattern for hook in hooks))

    return callback


# Gracefully reboot to reload code changes
# noinspection PyUnusedLocal
def reboot_callback(slack, msg, match):
    if msg["channel"] != channel_util.COMMAND_CENTER_ID:
        response = channel_util.NOT_ALLOWED_HERE
        reboot = False
    else:
        response = "Ok. Rebooting..."
        reboot = True

    slack_util.reply(slack, msg, response)
    if reboot:
        exit(0)


# Make hooks
bot_help_pattern = r"bot help"  # Can't init this directly, as it relies on us knowing all other hooks. handle in main
reboot_hook = slack_util.Hook(reboot_callback, pattern=r"reboot")
