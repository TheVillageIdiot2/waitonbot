import asyncio
from datetime import datetime
from typing import Optional, List

from slackclient import SlackClient

import channel_util
import house_management
import identifier
import slack_util


def seconds_until(target: datetime) -> float:
    curr = datetime.now()
    delta = target - curr
    return delta.seconds


class ItsTenPM(slack_util.Passive):
    async def run(self, slack: SlackClient) -> None:
        while True:
            # Get 10PM
            ten_pm = datetime.now().replace(hour=22, minute=0, second=0)

            # Find out how long until it, then sleep that long
            delay = seconds_until(ten_pm)
            await asyncio.sleep(delay)

            # Crow like a rooster
            slack_util.send_message(slack, "IT'S 10 PM!", channel_util.RANDOM)

            # Wait a while before trying it again, to prevent duplicates
            await asyncio.sleep(60)


class RemindJobs(slack_util.Passive):
    async def run(self, slack: SlackClient) -> None:
        while True:
            # Get the end of the current day (Say, 10PM)
            today_remind_time = datetime.now().replace(hour=22, minute=00, second=0)

            # Get the current day of week
            dow = ["Monday",
                   "Tuesday",
                   "Wednesday",
                   "Thursday",
                   "Friday",
                   "Saturday",
                   "Sunday"][datetime.now().weekday()]

            # Sleep until that time
            delay = seconds_until(today_remind_time)
            await asyncio.sleep(delay)

            # Now it is that time. Get the current jobs
            assigns = await house_management.import_assignments()

            # Filter to incomplete, and today
            def valid_filter(a: Optional[house_management.JobAssignment]):
                # If it doesn't exist, it a thot
                if a is None:
                    return False
                # If its not today, we shouldn't nag
                if a.job.day_of_week.lower() != dow.lower():
                    return False
                # If it is unassigned, we can't nag
                if a.assignee is None:
                    return False
                # If its been signed off, no need to nag
                if a.signer is not None:
                    return False
                # If the brother wasn't recognized, don't try nagging
                if not a.assignee.is_valid():
                    return False
                return True

            assigns: List[house_management.JobAssignment] = [a for a in assigns if valid_filter(a)]

            # Now, we want to nag each person. If we don't actually know who they are, so be it.
            print("Nagging!")
            for a in assigns:
                # Get the relevant slack ids
                assignee_ids = identifier.lookup_brother_userids(a.assignee)

                # For each, send them a DM
                success = False
                for slack_id in assignee_ids:
                    msg = "{}, you still need to do {}".format(a.assignee.name, a.job.pretty_fmt())
                    success = True
                    slack_util.send_message(slack, msg, slack_id)

                # Warn on failure
                if not success:
                    print("Tried to nag {} but couldn't find their slack id".format(a.assignee.name))

            # Take a break to ensure no double-shots
            await asyncio.sleep(10)
