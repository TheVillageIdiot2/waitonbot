from typing import Match, List

import slack_util


def list_hooks_callback_gen(hooks: List[slack_util.ChannelHook]) -> slack_util.Callback:
    # noinspection PyUnusedLocal
    async def callback(event: slack_util.Event, match: Match) -> None:
        slack_util.get_slack().reply(event, "\n".join(hook.patterns for hook in hooks))

    return callback


# Gracefully reboot to reload code changes
# noinspection PyUnusedLocal
async def reboot_callback(event: slack_util.Event, match: Match) -> None:
    response = "Ok. Rebooting..."
    slack_util.get_slack().reply(event, response)
    exit(0)


# Make hooks
reboot_hook = slack_util.ChannelHook(reboot_callback,
                                     patterns=r"reboot",
                                     channel_whitelist=["#command-center"])
