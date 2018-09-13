from collections import OrderedDict

import google_api as google  # For read drive
from slackclient import SlackClient  # Obvious
from slack_util import *

import scroll_util
import identifier
import re
import channel_util
import job_nagger

# Read api token from file
api_file = open("apitoken.txt", 'r')
SLACK_API = next(api_file).strip()
api_file.close()

# Read kill switch from file
kill_switch_file = open("killswitch.txt", 'r')
kill_switch = next(kill_switch_file).strip()
kill_switch_file.close()


def main():
    wrapper = ClientWrapper()

    # DEBUG: Add blanked handling
    # wrapper.add_hook(".*", print)

    # Add scroll handling
    wrapper.add_hook(scroll_util.command_pattern, scroll_util.callback)

    # Add id handling
    wrapper.add_hook(identifier.check_pattern, identifier.check_callback)
    wrapper.add_hook(identifier.identify_pattern, identifier.identify_callback)
    wrapper.add_hook(identifier.identify_other_pattern, identifier.identify_other_callback)
    wrapper.add_hook(identifier.name_pattern, identifier.name_callback)

    # Added channel utility
    wrapper.add_hook(channel_util.channel_check_pattern, channel_util.channel_check_callback)

    # Add test nagging functionality
    wrapper.add_hook(job_nagger.nag_pattern, job_nagger.nag_callback)

    # Add kill switch
    wrapper.add_hook(kill_switch, die)

    wrapper.listen()


def die(*args):
    print("Got kill switch")
    exit()


class ClientWrapper(object):
    def __init__(self):
        # Init slack
        self._slack = SlackClient(SLACK_API)

        # Hooks go regex -> callback on (slack, msg, match)
        self._hooks = OrderedDict()

    def add_hook(self, pattern, callback):
        self._hooks[pattern] = callback

    def listen(self):
        feed = message_stream(self._slack)
        for msg in feed:
            print(msg)

            # We only care about standard messages, not subtypes, as those usually just channel activity
            if msg.get("subtype") not in [None, "message_replied"]:
                continue

            # Handle Message
            text = msg['text'].strip()
            success = False
            for regex, callback in self._hooks.items():
                match = re.match(regex, text, flags=re.IGNORECASE)
                if match:
                    success = True
                    print("Matched on callback {}".format(callback))
                    callback(self._slack, msg, match)
                    break

            if not success:
                print("No hit on {}".format(text))


# run main
if __name__ == '__main__':
    main()
