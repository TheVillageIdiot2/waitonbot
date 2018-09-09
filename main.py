from collections import OrderedDict

import google_api as google  # For read drive
from slackclient import SlackClient  # Obvious
from slack_util import *

import scroll_util
import re

# Read api token from file
api_file = open("apitoken.txt", 'r')
SLACK_API = next(api_file).strip()
api_file.close()

# Read kill switch from file
kill_switch_file = open("killswitch.txt", 'r')
kill_switch = next(kill_switch_file).strip()
kill_switch_file.close()

# Authenticate, get sheets service. Done globally so we dont have to do this
# every fucking time, which is probably a bad idea
sheet_credentials = google.get_sheets_credentials()
sheet_service = google._init_sheets_service(sheet_credentials)


def main():
    wrapper = ClientWrapper()

    # DEBUG: Add blanked handling
    # wrapper.add_hook(".*", print)

    # Add scroll handling
    wrapper.add_hook(scroll_util.command_pattern, scroll_util.callback)

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
        self._slack.rtm_send_message(channel="@jacob henry", message="I'm back baby!")

        # Hooks go regex -> callback on (slack, msg, match)
        self._hooks = OrderedDict()

    def add_hook(self, pattern, callback):
        self._hooks[re.compile(pattern)] = callback

    def listen(self):
        feed = message_stream(self._slack)
        for msg in feed:
            # We only care about standard messages, not subtypes, as those usually just channel activity
            if msg.get("subtype"):
                continue

            # Handle Message
            text = msg['text'].strip()
            success = False
            for regex, callback in self._hooks.items():
                match = regex.match(text)
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
