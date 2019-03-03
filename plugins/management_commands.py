from typing import Match, List

import hooks
import client
import slack_util


def list_hooks_callback_gen(hooks: List[hooks.ChannelHook]) -> hooks.Callback:
    # noinspection PyUnusedLocal
    async def callback(event: slack_util.Event, match: Match) -> None:
        client.get_slack().reply(event, "\n".join(hook.patterns for hook in hooks))

    return callback


# Gracefully reboot to reload code changes
# noinspection PyUnusedLocal
async def reboot_callback(event: slack_util.Event, match: Match) -> None:
    response = "Ok. Rebooting..."
    client.get_slack().reply(event, response)
    exit(0)


# Make hooks
reboot_hook = hooks.ChannelHook(reboot_callback,
                                patterns=r"reboot",
                                channel_whitelist=["#command-center"])
