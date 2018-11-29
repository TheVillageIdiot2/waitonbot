from typing import Match, List

from slackclient import SlackClient

import channel_util
import slack_util


def list_hooks_callback_gen(hooks: List[slack_util.Hook]) -> slack_util.Callback:
    # noinspection PyUnusedLocal
    async def callback(slack, msg, match):
        slack_util.reply(slack, msg, "\n".join(hook.patterns for hook in hooks))

    return callback


# Gracefully reboot to reload code changes
# noinspection PyUnusedLocal
async def reboot_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    response = "Ok. Rebooting..."
    slack_util.reply(slack, msg, response)
    exit(0)


# Make hooks
reboot_hook = slack_util.Hook(reboot_callback,
                              patterns=r"reboot",
                              channel_whitelist=[channel_util.COMMAND_CENTER_ID])
