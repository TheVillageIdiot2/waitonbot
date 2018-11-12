import asyncio
from datetime import datetime

from slackclient import SlackClient

import channel_util
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
