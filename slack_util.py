from time import sleep
import re
import channel_util
from typing import Any

"""
Slack helpers. Separated for compartmentalization
"""


def reply(slack, msg, text, in_thread=True, to_channel=None):
    """
    Sends message with "text" as its content to the channel that message came from
    """
    # If no channel specified, just do same as msg
    if to_channel is None:
        to_channel = msg['channel']

    # Send in a thread by default
    if in_thread:
        thread = (msg.get("thread_ts")  # In-thread case - get parent ts
                  or msg.get("ts"))         # Not in-thread case - get msg itself ts
        slack.rtm_send_message(channel=to_channel, message=text, thread=thread)
    else:
        slack.rtm_send_message(channel=to_channel, message=text)


class SlackDebugCondom(object):
    def __init__(self, actual_slack):
        self.actual_slack = actual_slack

    def __getattribute__(self, name: str) -> Any:
        # Specialized behaviour
        if name == "rtm_send_message":
            # Flub some args
            def override_send_message(*args, **kwargs):
                print("Overriding: {} {}".format(args, kwargs))
                kwargs["channel"] = channel_util.BOTZONE
                kwargs["thread"] = None
                self.actual_slack.rtm_send_message(*args, **kwargs)
            return override_send_message
        else:
            # Default behaviour. Try to give the self first, elsewise give the child
            try:
                return super(SlackDebugCondom, self).__getattribute__(name)
            except AttributeError:
                return self.actual_slack.__getattribute__(name)


def message_stream(slack):
    """
    Generator that yields messages from slack.
    Messages are in standard api format, look it up.
    Checks on 2 second intervals (may be changed)
    """
    # Do forever
    while True:
        if slack.rtm_connect(with_team_state=False, auto_reconnect=True):
            print("Waiting for messages")
            while True:
                sleep(2)
                update = slack.rtm_read()
                for item in update:
                    if item.get('type') == 'message':
                        yield item

        sleep(15)
        print("Connection failed - retrying")


class Hook(object):
    def __init__(self, callback, pattern=None, channel_whitelist=None, channel_blacklist=None):
        # Save all
        self.pattern = pattern
        self.channel_whitelist = channel_whitelist
        self.channel_blacklist = channel_blacklist
        self.callback = callback

        # Remedy some sensible defaults
        if self.pattern is None:
            self.pattern = ".*"

        if self.channel_blacklist is None:
            import channel_util
            self.channel_blacklist = [channel_util.GENERAL]
        elif self.channel_whitelist is None:
            pass  # We leave as none to show no whitelisting in effect
        else:
            raise Exception("Cannot whitelist and blacklist")

    def check(self, slack, msg):
        # Fail if pattern invalid
        match = re.match(self.pattern, msg['text'], flags=re.IGNORECASE)
        if match is None:
            # print("Missed pattern")
            return False

        # Fail if whitelist defined, and we aren't there
        if self.channel_whitelist is not None and msg["channel"] not in self.channel_whitelist:
            # print("Missed whitelist")
            return False

        # Fail if blacklist defined, and we are there
        if self.channel_blacklist is not None and msg["channel"] in self.channel_blacklist:
            # print("Hit blacklist")
            return False

        # Otherwise do callback and return success
        print("Matched on pattern {} callback {}".format(self.pattern, self.callback))
        self.callback(slack, msg, match)
        return True
