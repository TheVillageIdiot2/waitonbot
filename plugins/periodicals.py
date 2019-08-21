import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List

import hooks
import slack_util
from plugins import identifier, job_commands, house_management, laundry, scroll_util
import client

def seconds_until(target: datetime) -> float:
    curr = datetime.now()

    # Compute seconds betwixt
    delta = target - curr
    ds = delta.seconds

    # Lower bound to 0
    if ds < 0:
        return 0
    else:
        return delta.seconds


class ItsTenPM(hooks.Passive):
    async def run(self) -> None:
        while True:
            # Get 10PM
            ten_pm = datetime.now().replace(hour=22, minute=0, second=0)

            # Find out how long until it, then sleep that long
            delay = seconds_until(ten_pm)
            await asyncio.sleep(delay)

            # Crow like a rooster
            client.get_slack().send_message("IT'S 10 PM!", client
                                            .get_slack()
                                            .get_conversation_by_name("#random").id)

            # Wait a while before trying it again, to prevent duplicates
            await asyncio.sleep(60)


# Shared behaviour
class JobNotifier:
    @staticmethod
    def get_day_of_week(time) -> str:
        """
        Gets the current day of week as a str
        """
        return ["Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday"][time.weekday()]

    @staticmethod
    def is_job_valid(a: Optional[house_management.JobAssignment]):
        # If it doesn't exist, it a thot
        if a is None:
            return False
        # If its not today, we shouldn't nag
        if a.job.day_of_week.lower() != JobNotifier.get_day_of_week(datetime.now()).lower():
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


class NotifyJobs(hooks.Passive, JobNotifier):
    # Auto-does the nag jobs thing
    async def run(self) -> None:
        while True:
            # Get the "Start" of the current day (Say, 10AM)
            next_remind_time = datetime.now().replace(hour=10, minute=00, second=0)

            # If we've accidentally made it in the past somehow, bump it up one date
            while datetime.now() > next_remind_time:
                next_remind_time += timedelta(days=1)

            # Sleep until that time
            delay = seconds_until(next_remind_time)
            await asyncio.sleep(delay)

            # Now it is that time. Nag the jobs
            await job_commands.nag_jobs(self.get_day_of_week(next_remind_time))

            # Sleep for a bit to prevent double shots
            await asyncio.sleep(10)


class RemindJobs(hooks.Passive, JobNotifier):
    async def run(self) -> None:
        while True:
            # Get the end of the current day (Say, 10PM)
            next_remind_time = datetime.now().replace(hour=22, minute=00, second=0)

            # If we've accidentally made it in the past somehow, bump it up one date
            while datetime.now() > next_remind_time:
                next_remind_time += timedelta(days=1)

            # Sleep until that time
            delay = seconds_until(next_remind_time)
            await asyncio.sleep(delay)

            # Now it is that time. Get the current jobs
            assigns = await house_management.import_assignments()

            # Filter to incomplete, and today
            assigns: List[house_management.JobAssignment] = [a for a in assigns if self.is_job_valid(a)]

            # Now, we want to nag each person. If we don't actually know who they are, so be it.
            logging.info("Scheduled reminding people who haven't yet done their jobs.")
            for a in assigns:
                # Get the relevant slack ids
                assignee_ids = await identifier.lookup_brother_userids(a.assignee)

                # For each, send them a DM
                success = False
                for slack_id in assignee_ids:
                    msg = "{}, you still need to do {}".format(a.assignee.name, a.job.pretty_fmt())
                    success = True
                    client.get_slack().send_message(msg, slack_id)

                # Warn on failure
                if not success:
                    logging.warning("Tried to nag {} but couldn't find their slack id".format(a.assignee.name))

            # Take a break to ensure no double-shots
            await asyncio.sleep(10)


class Updatinator(hooks.Passive):
    """
    Periodically updates the channels and users in the slack
    """

    def __init__(self, wrapper_to_update: client.ClientWrapper, interval_seconds: int):
        self.wrapper_target = wrapper_to_update
        self.interval = interval_seconds

    async def run(self):
        # Give time to warmup
        while True:
            self.wrapper_target.update_channels()
            self.wrapper_target.update_users()
            await asyncio.sleep(self.interval)


class TestPassive(hooks.Passive):
    """
    Stupid shit
    """

    async def run(self) -> None:
        lifespan = 60
        post_interval = 60

        def make_interactive_msg():
            # Send the message and recover the ts
            response = client.get_slack().send_message("Select an option:", "#botzone", blocks=[
                {
                    "type": "actions",
                    "block_id": "button_test",
                    "elements": [
                        {
                            "type": "button",
                            "action_id": "alpha_button",
                            "text": {
                                "type": "plain_text",
                                "text": "Alpha",
                                "emoji": False
                            }
                        },
                        {
                            "type": "button",
                            "action_id": "beta_button",
                            "text": {
                                "type": "plain_text",
                                "text": "Beta",
                                "emoji": False
                            }
                        }
                    ]
                }
            ])
            msg_ts = response["ts"]
            botzone = client.get_slack().get_conversation_by_name("#botzone")

            # Make our mappings
            button_responses = {
                "alpha_button": "You clicked alpha. Good work.",
                "beta_button": "You clicked beta. You must be so proud."
            }

            # Make our callbacks
            async def on_click(event: slack_util.Event, response_str: str):
                # Edit the message to show the result.
                client.get_slack().edit_message(response_str, event.conversation.conversation_id, event.message.ts, [])

            def on_expire():
                # Edit the message to show defeat.
                client.get_slack().edit_message("Timed out", botzone.id, msg_ts, [])

            # Add a listener
            listener = hooks.InteractionListener(on_click,
                                                 button_responses,
                                                 botzone,
                                                 msg_ts,
                                                 lifespan,
                                                 on_expire)
            client.get_slack().add_hook(listener)

        # Iterate editing the message every n seconds, for quite some time
        for i in range(10):
            make_interactive_msg()
            await asyncio.sleep(post_interval)

    def __init__(self):
        pass
