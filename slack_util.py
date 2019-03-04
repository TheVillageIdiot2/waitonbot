from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Optional, Generator, Callable, Union, Awaitable
from typing import TypeVar

from slackclient import SlackClient
from slackclient.client import SlackNotConnected

# Enable to do single-threaded and have better exceptions
import plugins
import client

DEBUG_MODE = False

"""
Objects to represent things within a slack workspace
"""


# noinspection PyUnresolvedReferences
@dataclass
class User:
    id: str
    name: str
    real_name: Optional[str]
    email: Optional[str]

    async def get_brother(self) -> Optional[plugins.scroll_util.Brother]:
        """
        Try to find the brother corresponding to this user.
        """
        return await plugins.identifier.lookup_slackid_brother(self.id)


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
        return client.get_slack().get_user(self.user_id)


Conversation = Union[Channel, DirectMessage]

"""
Objects to represent attributes an event may contain
"""


@dataclass
class Event:
    # Info on if this event ocurred in a particular conversation/channel, and if so which one
    conversation: Optional[ConversationContext] = None
    # Info on if a particular user caused this event, and if so which one
    user: Optional[UserContext] = None
    # Info on if this event was a someone posting a message. For contents see related
    post: Optional[PostMessageContext] = None
    # The content of the most relevant message to this event
    message: Optional[RelatedMessageContext] = None
    # Info if this event was threaded on a parent message, and if so what that message was
    thread: Optional[ThreadContext] = None
    # Info if this event was an interaction, and if so with what
    interaction: Optional[InteractionContext] = None
    # Info about regarding if bot caused this event, and if so which one
    bot: Optional[BotContext] = None


# If this was posted in a specific channel or conversation
@dataclass
class ConversationContext:
    conversation_id: str

    def get_conversation(self) -> Optional[Conversation]:
        return client.get_slack().get_conversation(self.conversation_id)


# If there is a specific user associated with this event
@dataclass
class UserContext:
    user_id: str

    def as_user(self) -> Optional[User]:
        return client.get_slack().get_user(self.user_id)


# Same but for bots
@dataclass
class BotContext:
    bot_id: str


# Whether this was a newly posted message
@dataclass
class PostMessageContext:
    pass


# Whether this event was related to a particular message, but not specifically posting it.
# To see if they posted it, check for PostMessageContext
@dataclass
class RelatedMessageContext:
    ts: str
    text: str


# Whether or not this is a threadable text message
@dataclass
class ThreadContext:
    thread_ts: str


@dataclass
class InteractionContext:
    response_url: str  # Used to confirm/respond to requests
    trigger_id: str  # Used to open popups
    block_id: str  # Identifies the block of the interacted component
    action_id: str  # Identifies the interacted component
    action_value: Optional[str]  # Identifies the selected value in the component. None for buttons


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
            event.message = RelatedMessageContext(update["ts"], update["text"])
            event.post = PostMessageContext()
        if "channel" in update:
            event.conversation = ConversationContext(update["channel"])
        if "user" in update:
            event.user = UserContext(update["user"])
        if "bot_id" in update:
            event.bot = BotContext(update["bot_id"])
        if "thread_ts" in update:
            event.thread = ThreadContext(update["thread_ts"])

    # TODO: Handle more types of events, including http data etc.

    return event


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
            client.get_slack().reply(self.event, "Error: {}".format(str(e)), True)
            raise e
