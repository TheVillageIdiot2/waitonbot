import re
from time import sleep, time
from typing import Any, Optional, Generator, Match, Callable, List, Coroutine, Union, TypeVar, Awaitable

from slackclient import SlackClient
from slackclient.client import SlackNotConnected

"""
Slack helpers. Separated for compartmentalization
"""


def reply(slack: SlackClient, msg: dict, text: str, in_thread: bool = True, to_channel: str = None) -> dict:
    """
    Sends message with "text" as its content to the channel that message came from
    """
    # If no channel specified, just do same as msg
    if to_channel is None:
        to_channel = msg['channel']

    # Send in a thread by default
    if in_thread:
        thread = (msg.get("thread_ts")  # In-thread case - get parent ts
                  or msg.get("ts"))  # Not in-thread case - get msg itself ts
        return send_message(slack, text, to_channel, thread=thread)
    else:
        return send_message(slack, text, to_channel)


def send_message(slack: SlackClient, text: str, channel: str, thread: str = None, broadcast: bool = False) -> dict:
    """
    Copy of the internal send message function of slack
    """
    kwargs = {"channel": channel, "text": text}
    if thread:
        kwargs["thread_ts"] = thread
        if broadcast:
            kwargs["reply_broadcast"] = True

    return slack.api_call("chat.postMessage", **kwargs)


def message_stream(slack: SlackClient) -> Generator[dict, None, None]:
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
                    update = slack.rtm_read()
                    for item in update:
                        if item.get('type') == 'message':
                            yield item
        except (SlackNotConnected, OSError) as e:
            print("Error while reading messages:")
            print(e)
        except (ValueError, TypeError):
            print("Malformed message... Restarting connection")

        sleep(5)
        print("Connection failed - retrying")


T = TypeVar("T")


class VerboseWrapper(Callable):
    """
    Generates exception-ready delegates.
    Warns of exceptions as they are passed through it, via responding to the given message.
    """
    def __init__(self, slack: SlackClient, command_msg: dict):
        self.slack = slack
        self.command_msg = command_msg

    async def __call__(self, awt: Awaitable[T]) -> T:
        try:
            return await awt
        except Exception as e:
            reply(self.slack, self.command_msg, "Error: {}".format(str(e)), True)
            raise e


MsgAction = Coroutine[Any, Any, None]
Callback = Callable[[SlackClient, dict, Match], MsgAction]


class DeadHook(Exception):
    pass


class AbsHook(object):
    def __init__(self, consumes_applicable: bool):
        # Whether or not messages that yield a coroutine should not be checked further
        self.consumes = consumes_applicable

    def try_apply(self, slack: SlackClient, msg: dict) -> Optional[Coroutine[None, None, None]]:
        raise NotImplementedError()


class Hook(AbsHook):
    def __init__(self,
                 callback: Callback,
                 patterns: Union[str, List[str]],
                 channel_whitelist: Optional[List[str]] = None,
                 channel_blacklist: Optional[List[str]] = None,
                 consumer: bool = True):
        super(Hook, self).__init__(consumer)

        # Save all
        if not isinstance(patterns, list):
            patterns = [patterns]

        self.patterns = patterns
        self.channel_whitelist = channel_whitelist
        self.channel_blacklist = channel_blacklist
        self.callback = callback

        # Remedy some sensible defaults
        if self.channel_blacklist is None:
            import channel_util
            self.channel_blacklist = [channel_util.GENERAL]
        elif self.channel_whitelist is None:
            pass  # We leave as none to show no whitelisting in effect
        else:
            raise ValueError("Cannot whitelist and blacklist")

    def try_apply(self, slack: SlackClient, msg: dict) -> Optional[Coroutine[None, None, None]]:
        """
        Returns whether a message should be handled by this dict, returning a Match if so, or None
        """
        # Fail if pattern invalid
        match = None
        for p in self.patterns:
            match = re.match(p, msg['text'], flags=re.IGNORECASE)
            if match is not None:
                break

        if match is None:
            return None

        # Fail if whitelist defined, and we aren't there
        if self.channel_whitelist is not None and msg["channel"] not in self.channel_whitelist:
            return None

        # Fail if blacklist defined, and we are there
        if self.channel_blacklist is not None and msg["channel"] in self.channel_blacklist:
            return None

        return self.callback(slack, msg, match)


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

    def try_apply(self, slack: SlackClient, msg: dict) -> Optional[Coroutine[None, None, None]]:
        # First check: are we dead of age yet?
        time_alive = time() - self.start_time
        should_expire = time_alive > self.lifetime

        # If so, give up the ghost
        if self.dead or should_expire:
            print("Reply waiter has expired after {} seconds".format(time_alive))
            raise DeadHook()

        # Otherwise proceed normally
        # Is the msg the one we care about? If not, ignore
        if msg.get("thread_ts", None) != self.thread_ts:
            return None

        # Does it match the regex? if not, ignore
        match = re.match(self.pattern, msg['text'], flags=re.IGNORECASE)
        if match:
            self.dead = True
            return self.callback(slack, msg, match)
        else:
            return None


class Passive(object):
    """
    Base class for Periodical tasks, such as reminders and stuff
    """

    async def run(self, slack: SlackClient) -> None:
        # Run this passive routed through the specified slack client.
        raise NotImplementedError()
