from collections import OrderedDict

import google_api as google  # For read drive
from slackclient import SlackClient  # Obvious
import slack_util

import scroll_util
import identifier
import re
import channel_util
import job_nagger
from dummy import FakeClient

# Read api token from file
api_file = open("apitoken.txt", 'r')
SLACK_API = next(api_file).strip()
api_file.close()

# Read kill switch from file
kill_switch_file = open("killswitch.txt", 'r')
kill_switch = next(kill_switch_file).strip()
kill_switch_file.close()

# Enable to use dummy
DEBUG_MODE = True


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

    # Add nagging functionality
    wrapper.add_hook(job_nagger.nag_pattern, job_nagger.nag_callback)

    # Add kill switch
    wrapper.add_hook(kill_switch, die)

    # Add help
    def list_hooks(slack, msg, match):
        slack_util.reply(slack, msg, "\n".join(wrapper.hooks.keys()))
    wrapper.add_hook("bot help", list_hooks)

    wrapper.listen()

# Callback to list command hooks


# Callback to die
def die(*args):
    print("Got kill switch")
    exit()


class ClientWrapper(object):
    def __init__(self):
        # Init slack
        if DEBUG_MODE:
            self.slack = FakeClient()
        else:
            self.slack = SlackClient(SLACK_API)

        # Hooks go regex -> callback on (slack, msg, match)
        self.hooks = OrderedDict()

    def add_hook(self, pattern, callback):
        self.hooks[pattern] = callback

    def listen(self):
        feed = slack_util.message_stream(self.slack)
        for msg in feed:
            print(msg)

            # We only care about standard messages, not subtypes, as those usually just channel activity
            if msg.get("subtype") is not None:
                continue

            # Never deal with general
            if msg.get("channel") == channel_util.GENERAL:
                continue

            # Handle Message
            text = msg['text'].strip()
            success = False
            for regex, callback in self.hooks.items():
                match = re.match(regex, text, flags=re.IGNORECASE)
                if match:
                    success = True
                    print("Matched on callback {}".format(callback))
                    callback(self.slack, msg, match)
                    break

            if not success:
                print("No hit on {}".format(text))


# run main
if __name__ == '__main__':
    main()
