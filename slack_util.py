from __future__ import annotations
from aiohttp import web
import asyncio
import re
import sys
import traceback
from dataclasses import dataclass
from time import sleep, time
from typing import List, Any, AsyncGenerator, Coroutine, TypeVar, Dict
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
    real_name: Optional[str]
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


@dataclass
class DirectMessage:
    id: str
    user_id: str

    def get_user(self) -> Optional[User]:
        """
        Lookup the user to which this DM corresponds.
        """
        return get_slack().get_user(self.user_id)


Conversation = Union[Channel, DirectMessage]

"""
Objects to represent attributes an event may contain
"""


@dataclass
class Event:
    conversation: Optional[ConversationContext] = None
    user: Optional[UserContext] = None
    message: Optional[MessageContext] = None
    thread: Optional[ThreadContext] = None
    interaction: Optional[InteractiveContext] = None


# If this was posted in a specific channel or conversation
@dataclass
class ConversationContext:
    conversation_id: str

    def get_conversation(self) -> Optional[Conversation]:
        return get_slack().get_conversation(self.conversation_id)


# If there is a specific user associated with this event
@dataclass
class UserContext:
    user_id: str

    def as_user(self) -> Optional[User]:
        return get_slack().get_user(self.user_id)


# Whether or not this is a threadable text message
@dataclass
class MessageContext:
    ts: str
    text: str


@dataclass
class ThreadContext:
    thread_ts: str


@dataclass
class InteractiveContext:
    response_url: str  # Used to confirm/respond to requests
    trigger_id: str  # Used to open popups
    block_id: str  # Identifies the block of the interacted component
    action_id: str  # Identifies the interacted component
    action_value: str  # Identifies the selected value in the component


# If a file was additionally shared
@dataclass
class File:
    pass


"""
Objects for interfacing easily with rtm steams, and handling async events
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
            if slack.rtm_connect(with_team_state=False, auto_reconnect=True):
                print("Waiting for messages")
                while True:
                    sleep(0.1)
                    update_list = slack.rtm_read()

                    # Handle each
                    for update in update_list:
                        print("Message received: {}".format(update))
                        yield message_dict_to_event(update)

        except (SlackNotConnected, OSError) as e:
            print("Error while reading messages:")
            print(e)
        except (ValueError, TypeError) as e:
            print("Malformed message... Restarting connection")
            print(e)

        sleep(5)
        print("Connection failed - retrying")


def message_dict_to_event(update: dict) -> Event:
    """
    Converts a dict update to an actual event.
    """
    event = Event()

    # Big logic folks
    if update["type"] == "message":
        # For now we only handle these basic types of messages involving text
        # TODO: Handle "unwrappeable" messages
        if "text" in update and "ts" in update:
            event.message = MessageContext(update["ts"], update["text"])
        if "channel" in update:
            event.conversation = ConversationContext(update["channel"])
        if "user" in update:
            event.user = UserContext(update["user"])
        if "thread_ts" in update:
            event.thread = ThreadContext(update["thread_ts"])

    # TODO: Handle more types of events, including http data etc.

    return event


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
        self.users: Dict[str, User] = {}
        self.conversations: Dict[str, Conversation] = {}

    # Scheduled/passive events handling
    def add_passive(self, per: Passive) -> None:
        self.passives.append(per)

    async def run_passives(self) -> None:
        """
        Run all currently added passives
        """
        awaitables = [p.run() for p in self.passives]
        await asyncio.gather(*awaitables)

    # Incoming slack hook handling
    def add_hook(self, hook: AbsHook) -> None:
        self.hooks.append(hook)

    async def handle_events(self) -> None:
        """
        Asynchronous tasks that eternally reads and responds to messages.
        """
        # Create a queue
        queue = asyncio.Queue()

        # Create a task to put rtm events to the queue
        rtm_task = asyncio.create_task(self.rtm_event_feed(queue))

        # Create a task to put http events to the queue
        http_task = asyncio.create_task(self.http_event_feed(queue))

        # Create a task to handle all other tasks
        async def handle_task_loop():
            async for t3 in self.spool_tasks(queue):
                sys.stdout.flush()
                if DEBUG_MODE:
                    await t3

        # Handle them all
        await asyncio.gather(rtm_task, http_task, handle_task_loop())

    async def rtm_event_feed(self, msg_queue: asyncio.Queue) -> None:
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
            next_event = await asyncio.get_running_loop().run_in_executor(None, get_one)
            await msg_queue.put(next_event)

    async def http_event_feed(self, event_queue: asyncio.Queue) -> None:
        # Create a callback to convert requests to events
        async def interr(request: web.Request):
            if request.can_read_body:
                # Get the payload
                body_dict = await request.json()
                payload = body_dict["payload"]

                # Handle each action separately
                if "actions" in payload:
                    for action in payload["actions"]:

                        # Start building the event
                        ev = Event()

                        # Get the user who clicked the button
                        ev.user = UserContext(payload["user"]["id"])

                        # Get the channel it was clicked in
                        ev.conversation = ConversationContext(payload["channel"]["id"])

                        # Get the message this button/action was attached to
                        ev.interaction = InteractiveContext(payload["response_url"],
                                                            payload["trigger_id"],
                                                            action["block_id"],
                                                            action["action_id"],
                                                            action["value"])

                        # Put it in the queue
                        await event_queue.put(ev)

                # Respond that everything is fine
                return web.Response(status=200)
            else:
                # If we can't read it, get mad
                return web.Response(status=400)

        # Create the server
        app = web.Application()
        app.add_routes([web.get('/bothttpcallback', interr)])

        # Asynchronously serve that boy up
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', 31019)
        await site.start()
        # print("Server up")
        # while True:
        #     await asyncio.sleep(30)

    async def spool_tasks(self, event_queue: asyncio.Queue) -> AsyncGenerator[asyncio.Task, Any]:
        """
        Read in from async event feed, and spool them out as async tasks
        """
        while True:
            event: Event = await event_queue.get()
            # Find which hook, if any, satisfies
            for hook in list(self.hooks):  # Note that we do list(self.hooks) to avoid edit-while-iterating issues
                # Try invoking each
                try:
                    # Try to make a coroutine handling the message
                    coro = hook.try_apply(event)

                    # If we get a coro back, then task it up and set consumption appropriately
                    if coro is not None:
                        print("Spawned task. Now {} running total.".format(len(asyncio.all_tasks())))
                        yield asyncio.create_task(_exception_printing_task(coro))
                        if hook.consumes:
                            break

                except DeadHook:
                    # If a hook wants to die, let it.
                    self.hooks.remove(hook)

    # Data getting/sending

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        return self.conversations.get(conversation_id)

    def get_conversation_by_name(self, conversation_identifier: str) -> Optional[Conversation]:
        # If looking for a direct message, first lookup user, then fetch
        if conversation_identifier[0] == "@":
            user_name = conversation_identifier

            # Find the user by their name
            raise NotImplementedError("There wasn't a clear use case for this yet, so we've opted to just not use it")

        # If looking for a channel, just lookup normally
        elif conversation_identifier[0] == "#":
            channel_name = conversation_identifier

            # Find the channel in the dict
            for channel in self.conversations.values():
                if channel.name == channel_name:
                    return channel

        # If it doesn't fit the above, we don't know how to process
        else:
            raise ValueError("Please give either an #channel-name or @user-name")

        # If we haven't returned already, give up and return None
        return None

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def get_user_by_name(self, user_name: str) -> Optional[User]:
        raise NotImplementedError()

    def api_call(self, api_method, **kwargs):
        return self.slack.api_call(api_method, **kwargs)

    # Simpler wrappers around message sending/replying

    def reply(self, event: Event, text: str, in_thread: bool = True) -> dict:
        """
        Replies to a message.
        Message must have a channel and message context.
        Returns the JSON response.
        """
        # Ensure we're actually replying to a valid message
        assert (event.conversation and event.message) is not None

        # Send in a thread by default
        if in_thread:
            # Figure otu what thread to send it to
            thread = event.message.ts
            if event.thread:
                thread = event.thread.thread_ts
            return self.send_message(text, event.conversation.conversation_id, thread=thread)
        else:
            return self.send_message(text, event.conversation.conversation_id)

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

    # Update slack data

    def update_channels(self):
        """
        Queries the slack API for all current channels
        """
        # Necessary because of pagination
        cursor = None

        # Make a new dict to use
        new_dict = {}

        # Iterate over results
        while True:
            # Set args depending on if a cursor exists
            args = {"limit": 1000, "types": "public_channel,private_channel,mpim,im"}
            if cursor:
                args["cursor"] = cursor

            channel_dicts = self.api_call("conversations.list", **args)

            # If the response is good, put its results to the dict
            if channel_dicts["ok"]:
                for channel_dict in channel_dicts["channels"]:
                    if channel_dict["is_im"]:
                        new_channel = DirectMessage(id=channel_dict["id"],
                                                    user_id="@" + channel_dict["user"])
                    else:
                        new_channel = Channel(id=channel_dict["id"],
                                              name="#" + channel_dict["name"])
                    new_dict[new_channel.id] = new_channel

                # Fetch the cursor
                cursor = channel_dicts.get("response_metadata").get("next_cursor")

                # If cursor is blank, we're done new channels, just give it up
                if cursor == "":
                    break

            else:
                print("Warning: failed to retrieve channels. Message: {}".format(channel_dicts))
                break
        self.conversations = new_dict

    def update_users(self):
        """
        Queries the slack API for all current users
        """
        # Necessary because of pagination
        cursor = None

        while True:
            # Set args depending on if a cursor exists
            args = {"limit": 1000}
            if cursor:
                args["cursor"] = cursor

            user_dicts = self.api_call("users.list", **args)

            # Make a new dict to use
            new_dict = {}

            # If the response is good:
            if user_dicts["ok"]:
                for user_dict in user_dicts["members"]:
                    new_user = User(id=user_dict.get("id"),
                                    name=user_dict.get("name"),
                                    real_name=user_dict.get("real_name"),
                                    email=user_dict.get("profile").get("email"))
                    new_dict[new_user.id] = new_user

                # Fetch the cursor
                cursor = user_dicts.get("response_metadata").get("next_cursor")

                # If cursor is blank, we're done new channels, just give it up
                if cursor == "":
                    break

            else:
                print("Warning: failed to retrieve users")
                break
        self.users = new_dict


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
                 consumer: bool = True,
                 allow_dms: bool = True):
        super(ChannelHook, self).__init__(consumer)

        # Save all
        if not isinstance(patterns, list):
            patterns = [patterns]

        self.patterns = patterns
        self.channel_whitelist = channel_whitelist
        self.channel_blacklist = channel_blacklist
        self.callback = callback
        self.allows_dms = allow_dms

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
        if not (event.conversation and event.message):
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
        if isinstance(event.conversation.get_conversation(), Channel):
            channel_name = event.conversation.get_conversation().name
        elif self.allows_dms:
            channel_name = "DIRECT_MSG"
        else:
            return None

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
