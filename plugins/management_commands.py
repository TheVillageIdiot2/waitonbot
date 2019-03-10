from typing import Match

import hooks
import client
import settings
import slack_util


# Gracefully reboot to reload code changes
# noinspection PyUnusedLocal
async def reboot_callback(event: slack_util.Event, match: Match) -> None:
    response = "Ok. Rebooting..."
    client.get_slack().reply(event, response)
    exit(0)


async def post_log_callback(event: slack_util.Event, match: Match) -> None:
    # Get the last 500 lines of log of the specified severity or higher
    count = 500
    lines = []

    # numerically rank the debug severity
    severity_codex = {
        "CRITICAL": 50,
        "ERROR": 40,
        "WARNING": 30,
        "INFO": 20,
        "DEBUG": 10,
        "NOTSET": 0
    }
    curr_rating = 0

    # Get the min rating if one exists
    min_rating = 0
    rating_str = match.group(1).upper().strip()
    for severity_name, severity_value in severity_codex.items():
        if severity_name in rating_str:
            min_rating = severity_value
            break

    with open(settings.LOGFILE, 'r') as f:
        for line in f:
            # Update the current rating if necessary
            if line[:3] == "#!#":
                for k, v in severity_codex.items():
                    if k in line:
                        curr_rating = v
                        break

            # Add the line if its severity is at or above the required minimum
            if curr_rating >= min_rating:
                lines.append(line)
                if len(lines) > count:
                    del lines[0]

        # Spew them out
        client.get_slack().reply(event, "```" + ''.join(lines) + "```")


# Make hooks
reboot_hook = hooks.ChannelHook(reboot_callback,
                                patterns=r"reboot",
                                channel_whitelist=["#command-center"])

log_hook = hooks.ChannelHook(post_log_callback,
                             patterns=["post logs(.*)", "logs(.*)", "post_logs(.*)"],
                             channel_whitelist=["#botzone"])
