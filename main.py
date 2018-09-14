from slackclient import SlackClient  # Obvious

import channel_util
import identifier
import job_nagger
import management_commands
import scroll_util
import slack_util
import slavestothemachine
from dummy import FakeClient

# Read api token from file
api_file = open("apitoken.txt", 'r')
SLACK_API = next(api_file).strip()
api_file.close()

# Enable to use dummy
DEBUG_MODE = False


def main():
    wrap = ClientWrapper()

    # DEBUG: Add blanked handling
    # wrapper.add_hook(".*", print)

    # Add scroll handling
    wrap.add_hook(scroll_util.scroll_hook)

    # Add id handling
    wrap.add_hook(identifier.check_hook)
    wrap.add_hook(identifier.identify_hook)
    wrap.add_hook(identifier.identify_other_hook)
    wrap.add_hook(identifier.name_hook)

    # Added channel utility
    wrap.add_hook(channel_util.channel_check_hook)

    # Add nagging functionality
    wrap.add_hook(job_nagger.nag_hook)

    # Add kill switch
    wrap.add_hook(management_commands.reboot_hook)

    # Add towel rolling
    wrap.add_hook(slavestothemachine.count_work_hook)
    wrap.add_hook(slavestothemachine.dump_work_hook)

    # Add help
    help_callback = management_commands.list_hooks_callback_gen(wrap.hooks)
    wrap.add_hook(slack_util.Hook(help_callback, pattern=management_commands.bot_help_pattern))

    wrap.listen()


# Callback to list command hooks

class ClientWrapper(object):
    def __init__(self):
        # Init slack
        if DEBUG_MODE:
            self.slack = FakeClient()
        else:
            self.slack = SlackClient(SLACK_API)

        # Hooks go regex -> callback on (slack, msg, match)
        self.hooks = []

    def add_hook(self, hook):
        self.hooks.append(hook)

    def listen(self):
        feed = slack_util.message_stream(self.slack)
        for msg in feed:
            print(msg)

            # We only care about standard messages, not subtypes, as those usually just channel activity
            if msg.get("subtype") is not None:
                continue

            # Never deal with general, EVER!
            if msg.get("channel") == channel_util.GENERAL:
                continue

            # Handle Message
            text = msg['text'].strip()
            success = False
            for hook in self.hooks:
                if hook.check(self.slack, msg):
                    success = True
                    break

            if not success:
                print("No hit on {}".format(text))


# run main
if __name__ == '__main__':
    main()
