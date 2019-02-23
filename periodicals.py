import asyncio
from datetime import datetime
from typing import Optional, List

import house_management
import identifier
import job_commands
import slack_util


def seconds_until(target: datetime) -> float:
    curr = datetime.now()
    delta = target - curr
    return delta.seconds


class ItsTenPM(slack_util.Passive):
    async def run(self) -> None:
        while True:
            # Get 10PM
            ten_pm = datetime.now().replace(hour=22, minute=0, second=0)

            # Find out how long until it, then sleep that long
            delay = seconds_until(ten_pm)
            await asyncio.sleep(delay)

            # Crow like a rooster
            slack_util.get_slack().send_message("IT'S 10 PM!", slack_util.get_slack().get_conversation_by_name("#random").id)

            # Wait a while before trying it again, to prevent duplicates
            await asyncio.sleep(60)


# Shared behaviour
class JobNotifier:
    @staticmethod
    def get_day_of_week() -> str:
        """
        Gets the current day of week as a str
        """
        return ["Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday"][datetime.now().weekday()]

    @staticmethod
    def is_job_valid(a: Optional[house_management.JobAssignment]):
        # If it doesn't exist, it a thot
        if a is None:
            return False
        # If its not today, we shouldn't nag
        if a.job.day_of_week.lower() != JobNotifier.get_day_of_week().lower():
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


class NotifyJobs(slack_util.Passive, JobNotifier):
    async def run(self) -> None:
        while True:
            # Get the "Start" of the current day (Say, 10AM)
            today_remind_time = datetime.now().replace(hour=10, minute=00, second=0)

            # Sleep until that time
            delay = seconds_until(today_remind_time)
            await asyncio.sleep(delay)

            # Now it is that time. Nag the jobs
            job_commands.nag_jobs(self.get_day_of_week())

            # Sleep for a bit to prevent double shots
            await asyncio.sleep(10)


class RemindJobs(slack_util.Passive, JobNotifier):
    async def run(self) -> None:
        while True:
            # Get the end of the current day (Say, 10PM)
            today_remind_time = datetime.now().replace(hour=22, minute=00, second=0)

            # Sleep until that time
            delay = seconds_until(today_remind_time)
            await asyncio.sleep(delay)

            # Now it is that time. Get the current jobs
            assigns = await house_management.import_assignments()

            # Filter to incomplete, and today
            assigns: List[house_management.JobAssignment] = [a for a in assigns if self.is_job_valid(a)]

            # Now, we want to nag each person. If we don't actually know who they are, so be it.
            print("Reminding!")
            for a in assigns:
                # Get the relevant slack ids
                assignee_ids = await identifier.lookup_brother_userids(a.assignee)

                # For each, send them a DM
                success = False
                for slack_id in assignee_ids:
                    msg = "{}, you still need to do {}".format(a.assignee.name, a.job.pretty_fmt())
                    success = True
                    slack_util.get_slack().send_message(msg, slack_id)

                # Warn on failure
                if not success:
                    print("Tried to nag {} but couldn't find their slack id".format(a.assignee.name))

            # Take a break to ensure no double-shots
            await asyncio.sleep(10)


class Updatinator(slack_util.Passive):
    """
    Periodically updates the channels and users in the slack
    """
    def __init__(self, wrapper_to_update: slack_util.ClientWrapper, interval_seconds: int):
        self.wrapper_target = wrapper_to_update
        self.interval = interval_seconds

    async def run(self):
        # Give time to warmup
        while True:
            self.wrapper_target.update_channels()
            self.wrapper_target.update_users()
            await asyncio.sleep(self.interval)
