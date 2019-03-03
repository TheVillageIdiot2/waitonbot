from __future__ import annotations

import re
from time import time
from typing import Match, Any, Coroutine, Callable, Optional, Union, List

import slack_util

# Return type of an event callback
MsgAction = Coroutine[Any, Any, None]

# Type signature of an event callback function
Callback = Callable[[slack_util.Event, Match], MsgAction]

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

    def try_apply(self, event: slack_util.Event) -> Optional[MsgAction]:
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
    """

    def __init__(self, callback: Callback, pattern: str, thread_ts: str, lifetime: float):
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

