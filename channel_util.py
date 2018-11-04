from typing import Match

from slackclient import SlackClient

import slack_util

# Useful channels
GENERAL = "C0CFHPNEM"
COMMAND_CENTER_ID = "GCR631LQ1"
SLAVES_TO_THE_MACHINE_ID = "C9WUQBYNP"
BOTZONE = "C3BF2MFKM"
HOUSEJOBS = "CDWDDTAT0"


# Callback for telling what channel we in
def channel_check_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    # Sets the users scroll
    rest_of_msg = match.group(1).strip()
    rest_of_msg = rest_of_msg.replace("<", "lcaret")
    rest_of_msg = rest_of_msg.replace(">", "rcaret")

    # Respond
    response = ""
    response += "Channel id: {}\n".format(msg["channel"])
    response += "Escaped message: {}\n".format(rest_of_msg)
    slack_util.reply(slack, msg, response)


channel_check_hook = slack_util.Hook(channel_check_callback, pattern=r"channel id\s*(.*)")
