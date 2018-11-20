import asyncio
from typing import List, Any, AsyncGenerator

from slackclient import SlackClient  # Obvious

import channel_util
import slack_util

# Read the API token
api_file = open("apitoken.txt", 'r')
SLACK_API = next(api_file).strip()
api_file.close()

# Enable to do single-threaded and have better exceptions
DEBUG_MODE = False


class ClientWrapper(object):
    """
    Essentially the main state object.
    We only ever expect one of these.
    Holds a slack client, and handles messsages.
    """

    def __init__(self):
        # Init slack
        self.slack = SlackClient(SLACK_API)

        # Hooks go regex -> callback on (slack, msg, match)
        self.hooks: List[slack_util.AbsHook] = []

        # Periodicals are just wrappers around an iterable, basically
        self.passives: List[slack_util.Passive] = []

    # Scheduled events handling
    def add_passive(self, per: slack_util.Passive) -> None:
        self.passives.append(per)

    async def run_passives(self) -> None:
        # Make a task to repeatedly spawn each event
        awaitables = [p.run(self.slack) for p in self.passives]
        await asyncio.gather(*awaitables)

    # Message handling
    def add_hook(self, hook: slack_util.AbsHook) -> None:
        self.hooks.append(hook)

    async def respond_messages(self) -> None:
        """
        Asynchronous tasks that eternally reads and responds to messages.
        """
        async for t in self.spool_tasks():
            if DEBUG_MODE:
                await t
            print("Handling a message...!")

    async def spool_tasks(self) -> AsyncGenerator[asyncio.Task, Any]:
        async for msg in self.async_message_feed():
            # Preprocess msg
            # We only care about standard messages, not subtypes, as those usually just channel activity
            if msg.get("subtype") is not None:
                continue

            # Never deal with general, EVER!
            if msg.get("channel") == channel_util.GENERAL:
                continue

            # Strip garbage
            msg['text'] = msg['text'].strip()
            print("Recv: \"{}\"".format(msg['text']))
            print(msg)

            # Msg is good
            # Find which hook, if any, satisfies
            for hook in self.hooks:
                # Try invoking each
                try:
                    # Try to make a coroutine handling the message
                    coro = hook.try_apply(self.slack, msg)

                    # If we get a coro back, then task it up and set consumption appropriately
                    if coro is not None:
                        print("Spawned task")
                        yield asyncio.create_task(coro)
                        if hook.consumes:
                            break

                except slack_util.DeadHook:
                    # If a hook wants to die, let it.
                    self.hooks.remove(hook)
            print("Done spawning tasks")

    async def async_message_feed(self) -> AsyncGenerator[dict, None]:
        """
        Async wrapper around the message feed.
        Yields messages awaitably forever.
        """
        # Create the msg feed
        feed = slack_util.message_stream(self.slack)

        # Create a simple callable that gets one message from the feed
        def get_one():
            return next(feed)

        # Continuously yield async threaded tasks that poll the feed
        while True:
            yield await asyncio.get_running_loop().run_in_executor(None, get_one)


_singleton = ClientWrapper()


def get_client_wrapper() -> ClientWrapper:
    return _singleton
