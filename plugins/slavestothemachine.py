import re
import textwrap
from typing import Match

import hooks
from plugins import house_management
import client
import slack_util
from plugins.scroll_util import Brother

counted_data = ["flaked", "rolled", "replaced", "washed", "dried"]
lookup_format = "{}\s+(\d+)"


def fmt_work_dict(work_dict: dict) -> str:
    return ",\n".join(["{} × {}".format(job, count) for job, count in sorted(work_dict.items())])


# noinspection PyUnusedLocal
async def count_work_callback(event: slack_util.Event, match: Match) -> None:
    # If no user, continue
    if event.user is None:
        return

    # If bot, continue
    if event.bot is not None:
        return

    # Make an error wrapper
    verb = slack_util.VerboseWrapper(event)

    # Tidy the text
    text = event.message.text.strip().lower()

    # Couple things to work through.
    # One: Who sent the message?
    who_wrote = await verb(event.user.as_user().get_brother())
    who_wrote_label = "{} [{}]".format(who_wrote.name, who_wrote.scroll)

    # Two: What work did they do?
    new_work = {}
    for job in counted_data:
        pattern = lookup_format.format(job)
        match = re.search(pattern, text)
        if match:
            new_work[job] = int(match.group(1))

    # Three: check if we found anything
    if len(new_work) == 0:
        if re.search(r'\s\d\s', text) is not None:
            client.get_slack().reply(event,
                                     "If you were trying to record work, it was not recognized.\n"
                                     "Use words {} or work will not be recorded".format(counted_data))
        return

    # Four: Knowing they did something, record to total work
    contribution_count = sum(new_work.values())
    new_total = await verb(record_towel_contribution(who_wrote, contribution_count))

    # Five, congratulate them on their work!
    congrats = textwrap.dedent("""{} recorded work:
    {}
    Net increase in points: {}
    Total points since last reset: {}""".format(who_wrote_label,
                                                fmt_work_dict(new_work),
                                                contribution_count,
                                                new_total))
    client.get_slack().reply(event, congrats)


async def record_towel_contribution(for_brother: Brother, contribution_count: int) -> int:
    """
    Grants <count> contribution point to the specified user.
    Returns the new total.
    """
    # Import house points
    headers, points = await house_management.import_points()

    # Find the brother
    for p in points:
        if p is None or p.brother != for_brother:
            continue

        # If found, mog with more points
        p.towel_contribution_count += contribution_count

        # Export
        house_management.export_points(headers, points)

        # Return the new total
        return p.towel_contribution_count

    # If not found, get mad!
    raise KeyError("No score entry found for brother {}".format(for_brother))


# Make dem HOOKs
count_work_hook = hooks.ChannelHook(count_work_callback,
                                    patterns=".*",
                                    channel_whitelist=["#slavestothemachine"],
                                    consumer=False)
