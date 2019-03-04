from __future__ import annotations

import re
from time import time
from typing import Match, Any, Coroutine, Callable, Optional, Union, List, TypeVar, Dict

import slack_util

# Return type of an event callback
MsgAction = Coroutine[Any, Any, None]

# Type signature of a message event callback function, for convenience
MsgCallback = Callable[[slack_util.Event, Match], MsgAction]

"""
Hooks
"""


# Signal exception to be raised when a hook has died
class HookDeath(Exception):
    pass


# Abstract hook parent class
class AbsHook(object):
    def __init__(self, consumes_applicable: bool):
        # Whether or not messages that yield a coroutine should not be checked further
        self.consumes = consumes_applicable

    def try_apply(self, event: slack_util.Event) -> Optional[MsgAction]:
        raise NotImplementedError()


class ChannelHook(AbsHook):
    """
    Hook that handles messages in a variety of channels.
    Guarantees prescence of Post, Related, Conversation, and User
    """

    def __init__(self,
                 callback: MsgCallback,
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

    def try_apply(self, event: slack_util.Event) -> Optional[MsgAction]:
        """
        Returns whether a message should be handled by this dict, returning a Match if so, or None
        """
        # Ensure that this is an event in a specific channel, with a text component
        if not (event.conversation and event.post and event.message and event.user):
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
        if isinstance(event.conversation.get_conversation(), slack_util.Channel):
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
    Guarantees presence of Post, Message, Thread, User, and Conversation.
    As such, it ignores bots.
    """

    def __init__(self, callback: MsgCallback, pattern: str, thread_ts: str, lifetime: float):
        super().__init__(True)
        self.callback = callback
        self.pattern = pattern
        self.thread_ts = thread_ts
        self.lifetime = lifetime
        self.start_time = time()
        self.dead = False

    def try_apply(self, event: slack_util.Event) -> Optional[MsgAction]:
        # First check: are we dead of age yet?
        time_alive = time() - self.start_time
        should_expire = time_alive > self.lifetime

        # If so, give up the ghost
        if self.dead or should_expire:
            raise HookDeath()

        # Next make sure we're actually a message
        if not (event.post and event.post and event.thread and event.conversation and event.user):
            return None

        # Otherwise proceed normally
        # Is the msg the one we care about? If not, ignore
        if event.thread.thread_ts != self.thread_ts:
            return None

        # Does it match the regex? if not, ignore
        match = re.match(self.pattern, event.post.text.strip(), flags=re.IGNORECASE)
        if match:
            self.dead = True
            return self.callback(event, match)
        else:
            return None


# The associated generic type of a button - value mapping
ActionVal = TypeVar("T")


class InteractionListener(AbsHook):
    """
    Listens for replies on buttons.
    Guarantees Interaction, Message, User, and Conversation
    For fields that don't have a value of their own (such as buttons),
    one can provide a mapping of action_ids to values.
    In either case, the value is fed as a parameter to the callback
    """

    def __init__(self,
                 callback: Callable[[slack_util.Event, Union[ActionVal, str]], MsgAction],
                 action_bindings: Optional[Dict[str, ActionVal]],
                 # The action_id -> value mapping. Value fed to callback
                 message_ts: str,  # Which message contains the block we care about
                 lifetime: float,  # How long to keep listening
                 on_death: Optional[Callable[[], None]]  # Function to call on death. For instance, if you want to delete the message
                 ):
        super().__init__(True)
        self.callback = callback
        self.bindings = action_bindings
        self.message_ts = message_ts
        self.lifetime = lifetime
        self.start_time = time()
        self.on_death = on_death
        self.dead = False

    def try_apply(self, event: slack_util.Event) -> Optional[MsgAction]:
        # First check: are we dead of age yet?
        time_alive = time() - self.start_time
        should_expire = time_alive > self.lifetime

        # If so, give up the ghost
        if self.dead or should_expire:
            if self.on_death:
                self.on_death()
            raise HookDeath()

        # Next make sure we're actually a message
        if not (event.interaction and event.message):
            return None

        # Otherwise proceed normally
        # Is the msg the one we care about? If not, ignore
        if event.message.ts != self.message_ts:
            return None

        # Lookup the binding if we can/need to
        value = event.interaction.action_value
        if value is None and self.bindings is not None:
            value = self.bindings.get(event.interaction.action_id)

        # If the value is still none, we have an issue!
        if value is None:
            raise ValueError("Couldn't find an appropriate value for interaction {}".format(event.interaction))

        # Call the callback
        return self.callback(event, value)


class Passive(object):
    """
    Base class for Periodical tasks, such as reminders and stuff
    """

    async def run(self) -> None:
        # Run this passive routed through the specified slack client.
        raise NotImplementedError()
