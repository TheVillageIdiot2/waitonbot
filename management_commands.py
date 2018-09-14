import identifier
import scroll_util
import slack_util
import google_api
import channel_util

bot_help_pattern = r"bot help"


def list_hooks_callback_gen(hook_strings):
    def callback(slack, msg, match):
        slack_util.reply(slack, msg, "\n".join(hook_strings))

    return callback


# Gracefully reboot to reload code changes
reboot_pattern = r"reboot"


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
