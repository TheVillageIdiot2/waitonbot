from time import sleep

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
        slack.rtm_send_message(channel=to_channel, message=text, thread=msg['ts'])
    else:
        slack.rtm_send_message(channel=to_channel, message=text)


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