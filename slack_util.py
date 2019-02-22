from __future__ import annotations

import asyncio
import re
import sys
import traceback
from dataclasses import dataclass
from time import sleep, time
from typing import List, Any, AsyncGenerator, Coroutine, TypeVar
from typing import Optional, Generator, Match, Callable, Union, Awaitable

from slackclient import SlackClient
from slackclient.client import SlackNotConnected

# Enable to do single-threaded and have better exceptions
import identifier
import scroll_util

DEBUG_MODE = False

"""
Objects to represent things within a slack workspace
"""


@dataclass
class User:
    id: str
    name: str
    real_name: str
    email: Optional[str]

    async def get_brother(self) -> Optional[scroll_util.Brother]:
        """
        Try to find the brother corresponding to this user.
        """
        return await identifier.lookup_slackid_brother(self.id)


@dataclass
class Channel:
    id: str
    name: str
    purpose: str
    members: List[User]


"""
Objects to represent attributes an event may contain
"""


@dataclass
class Event:
    channel: Optional[ChannelContext] = None
    user: Optional[UserContext] = None
    message: Optional[MessageContext] = None
    thread: Optional[ThreadContext] = None


# If this was posted in a specific channel or conversation
@dataclass
class ChannelContext:
    channel_id: str

    def get_channel(self) -> Channel:
        raise NotImplementedError()


# If there is a specific user associated with this event
@dataclass
class UserContext:
    user_id: str

    def as_user(self) -> User:
        raise NotImplementedError()


# Whether or not this is a threadable text message
@dataclass
class MessageContext:
    ts: str
    text: str


@dataclass
class ThreadContext:
    thread_ts: str
    parent_ts: str


# If a file was additionally shared
@dataclass
class File:
    pass


"""
Objects for interfacing easily with rtm steams 
"""


def message_stream(slack: SlackClient) -> Generator[Event, None, None]:
    """
    Generator that yields messages from slack.
    Messages are in standard api format, look it up.
    Checks on 2 second intervals (may be changed)
    """
    # Do forever
    while True:
        try:
            if slack.rtm_connect(with_team_state=True, auto_reconnect=True):
                print("Waiting for messages")
                while True:
                    sleep(0.1)
                    update_list = slack.rtm_read()

                    # Handle each
                    for update in update_list:
                        print("Message received: {}".format(update))
                        event = Event()

                        # Big logic folks
                        if update["type"] == "message":
                            event.message = MessageContext(update["ts"], update["text"])
                            event.channel = ChannelContext(update["channel"])
                            event.user = UserContext(update["user"])

                        # TODO: Handle more types
                        # We need to

                        yield event

        except (SlackNotConnected, OSError) as e:
            print("Error while reading messages:")
            print(e)
        except (ValueError, TypeError) as e:
            print("Malformed message... Restarting connection")
            print(e)

        sleep(5)
        print("Connection failed - retrying")


"""
Objects to wrap slack connections
"""
# Read the API token
api_file = open("apitoken.txt", 'r')
SLACK_API = next(api_file).strip()
api_file.close()


class ClientWrapper(object):
    """
    Essentially the main state object.
    We only ever expect one of these per api token.
    Holds a slack client, and handles messsages.
    """

    def __init__(self, api_token):
        # Init slack
        self.slack = SlackClient(api_token)

        # Hooks go regex -> callback on (slack, msg, match)
        self.hooks: List[AbsHook] = []

        # Periodicals are just wrappers around an iterable, basically
        self.passives: List[Passive] = []

        # Cache users and channels
        self.users: dict = {}
        self.channels: dict = {}

    # Scheduled events handling
    def add_passive(self, per: Passive) -> None:
        self.passives.append(per)

    async def run_passives(self) -> None:
        """
        Run all currently added passives
        """
        awaitables = [p.run() for p in self.passives]
        await asyncio.gather(*awaitables)

    # Message handling
    def add_hook(self, hook: AbsHook) -> None:
        self.hooks.append(hook)

    async def respond_messages(self) -> None:
        """
        Asynchronous tasks that eternally reads and responds to messages.
        """
        async for t in self.spool_tasks():
            sys.stdout.flush()
            if DEBUG_MODE:
                await t

    async def spool_tasks(self) -> AsyncGenerator[asyncio.Task, Any]:
        async for event in self.async_event_feed():
            # Find which hook, if any, satisfies
            for hook in list(self.hooks):  # Note that we do list(self.hooks) to avoid edit-while-iterating issues
                # Try invoking each
                try:
                    # Try to make a coroutine handling the message
                    coro = hook.try_apply(event)

                    # If we get a coro back, then task it up and set consumption appropriately
                    if coro is not None:
                        print("Spawned task")
                        yield asyncio.create_task(_exception_printing_task(coro))
                        if hook.consumes:
                            break

                except DeadHook:
                    # If a hook wants to die, let it.
                    self.hooks.remove(hook)
            print("Done spawning tasks. Now {} running total.".format(len(asyncio.all_tasks())))

    async def async_event_feed(self) -> AsyncGenerator[Event, None]:
        """
        Async wrapper around the message feed.
        Yields messages awaitably forever.
        """
        # Create the msg feed
        feed = message_stream(self.slack)

        # Create a simple callable that gets one message from the feed
        def get_one():
            return next(feed)

        # Continuously yield async threaded tasks that poll the feed
        while True:
            yield await asyncio.get_running_loop().run_in_executor(None, get_one)

    def get_channel(self, channel_id: str) -> Optional[Channel]:
        return self.channels.get(channel_id)

    def get_channel_by_name(self, channel_name: str) -> Optional[Channel]:
        # Find the channel in the dict
        for v in self.channels.values():
            if v.name == channel_name:
                return v
        return None

    def get_user(self, user_id: str) -> Optional[Channel]:
        return self.users.get(user_id)

    def api_call(self, api_method, **kwargs):
        return self.slack.api_call(api_method, **kwargs)

    def reply(self, event: Event, text: str, in_thread: bool = True) -> dict:
        """
        Replies to a message.
        Message must have a channel and message context.
        Returns the JSON response.
        """
        # Ensure we're actually replying to a valid message
        assert (event.channel and event.message) is not None

        # Send in a thread by default
        if in_thread:
            # Figure otu what thread to send it to
            thread = event.message.ts
            if event.thread:
                thread = event.thread.thread_ts
            return self.send_message(text, event.channel.channel_id, thread=thread)
        else:
            return self.send_message(text, event.channel.channel_id)

    def send_message(self, text: str, channel_id: str, thread: str = None, broadcast: bool = False) -> dict:
        """
        Copy of the internal send message function of slack, with some helpful options.
        Returns the JSON response.
        """
        kwargs = {"channel": channel_id, "text": text}
        if thread:
            kwargs["thread_ts"] = thread
            if broadcast:
                kwargs["reply_broadcast"] = True

        return self.api_call("chat.postMessage", **kwargs)


# Create a single instance of the client wrapper
_singleton = ClientWrapper(SLACK_API)


def get_slack() -> ClientWrapper:
    return _singleton


# Return type of an event callback
MsgAction = Coroutine[Any, Any, None]

# Type signature of an event callback function
Callback = Callable[[Event, Match], MsgAction]

"""
Hooks
"""


# Signal exception to be raised when a hook has died
class DeadHook(Exception):
    pass


# Abstract hook parent class
class AbsHook(object):
    def __init__(self, consumes_applicable: bool):
        # Whether or not messages that yield a coroutine should not be checked further
        self.consumes = consumes_applicable

    def try_apply(self, event: Event) -> Optional[MsgAction]:
        raise NotImplementedError()


class ChannelHook(AbsHook):
    """
    Hook that handles messages in a variety of channels
    """

    def __init__(self,
                 callback: Callback,
                 patterns: Union[str, List[str]],
                 channel_whitelist: Optional[List[str]] = None,
                 channel_blacklist: Optional[List[str]] = None,
                 consumer: bool = True):
        super(ChannelHook, self).__init__(consumer)

        # Save all
        if not isinstance(patterns, list):
            patterns = [patterns]

        self.patterns = patterns
        self.channel_whitelist = channel_whitelist
        self.channel_blacklist = channel_blacklist
        self.callback = callback

        # Remedy some sensible defaults
        if self.channel_blacklist is None:
            self.channel_blacklist = ["#general"]
        elif self.channel_whitelist is None:
            pass  # We leave as none to show no whitelisting in effect
        else:
            raise ValueError("Cannot whitelist and blacklist")

    def try_apply(self, event: Event) -> Optional[MsgAction]:
        """
        Returns whether a message should be handled by this dict, returning a Match if so, or None
        """
        # Ensure that this is an event in a specific channel, with a text component
        if not (event.channel and event.message):
            return None

        # Fail if pattern invalid
        match = None
        for p in self.patterns:
            match = re.match(p, event.message.text.strip(), flags=re.IGNORECASE)
            if match is not None:
                break

        if match is None:
            return None

        # Get the channel name
        channel_name = event.channel.get_channel().name

        # Fail if whitelist defined, and we aren't there
        if self.channel_whitelist is not None and channel_name not in self.channel_whitelist:
            return None

        # Fail if blacklist defined, and we are there
        if self.channel_blacklist is not None and channel_name in self.channel_blacklist:
            return None

        return self.callback(event, match)


class ReplyWaiter(AbsHook):
    """
    A special hook that only cares about replies to a given message.
    """

    def __init__(self, callback: Callback, pattern: str, thread_ts: str, lifetime: float):
        super().__init__(True)
        self.callback = callback
        self.pattern = pattern
        self.thread_ts = thread_ts
        self.lifetime = lifetime
        self.start_time = time()
        self.dead = False

    def try_apply(self, event: Event) -> Optional[MsgAction]:
        # First check: are we dead of age yet?
        time_alive = time() - self.start_time
        should_expire = time_alive > self.lifetime

        # If so, give up the ghost
        if self.dead or should_expire:
            raise DeadHook()

        # Next make sure we're actually a message
        if not (event.message and event.thread):
            return None

        # Otherwise proceed normally
        # Is the msg the one we care about? If not, ignore
        if event.thread.thread_ts != self.thread_ts:
            return None

        # Does it match the regex? if not, ignore
        match = re.match(self.pattern, event.message.text.strip(), flags=re.IGNORECASE)
        if match:
            self.dead = True
            return self.callback(event, match)
        else:
            return None


class Passive(object):
    """
    Base class for Periodical tasks, such as reminders and stuff
    """

    async def run(self) -> None:
        # Run this passive routed through the specified slack client.
        raise NotImplementedError()


"""
Methods for easily responding to messages, etc.
"""

T = TypeVar("T")


class VerboseWrapper(Callable):
    """
    Generates exception-ready delegates.
    Warns of exceptions as they are passed through it, via responding to the given message.
    """

    def __init__(self, event: Event):
        self.event = event

    async def __call__(self, awt: Awaitable[T]) -> T:
        try:
            return await awt
        except Exception as e:
            get_slack().reply(self.event, "Error: {}".format(str(e)), True)
            raise e


"""
Miscellania
"""

A, B, C = TypeVar("A"), TypeVar("B"), TypeVar("C")


# Prints exceptions instead of silently dropping them in async tasks
async def _exception_printing_task(c: Coroutine[A, B, C]) -> Coroutine[A, B, C]:
    # Print exceptions as they pass through
    try:
        return await c
    except Exception:
        traceback.print_exc()
        raise
