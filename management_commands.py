from typing import Match, List

from slackclient import SlackClient

import channel_util
import slack_util


def list_hooks_callback_gen(hooks: List[slack_util.Hook]):
    # noinspection PyUnusedLocal
    def callback(slack, msg, match):
        slack_util.reply(slack, msg, "\n".join(hook.pattern for hook in hooks))

    return callback


# Gracefully reboot to reload code changes
# noinspection PyUnusedLocal
def reboot_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    response = "Ok. Rebooting..."
    slack_util.reply(slack, msg, response)
    exit(0)


# Make hooks
bot_help_pattern = r"bot help"  # Can't init this directly, as it relies on us knowing all other hooks. handle in main
reboot_hook = slack_util.Hook(reboot_callback, pattern=r"reboot", channel_whitelist=[channel_util.COMMAND_CENTER_ID])
