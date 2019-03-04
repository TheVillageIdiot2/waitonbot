from typing import Match

import hooks
import client
import slack_util


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
