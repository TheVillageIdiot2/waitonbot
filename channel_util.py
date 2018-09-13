
import shelve
import slack_util

DB_NAME = "channel_priveleges"

# Define our patterns
channel_check_pattern = r"channel id\s*(.*)"
# channel_check_pattern = r"channel id <#(.*)>"
# identify_other_pattern = r"<@(.*)>\s+has scroll\s+(.*)"


def channel_check_callback(slack, msg, match):
    # Sets the users scroll
    # with shelve.open(DB_NAME) as db:

    rest_of_msg = match.group(1).strip()
    rest_of_msg = rest_of_msg.replace("<", "lcaret")
    rest_of_msg = rest_of_msg.replace(">", "rcaret")

    # Respond
    response = ""
    response += "Channel id: {}\n".format(msg["channel"])
    response += "Escaped message: {}\n".format(rest_of_msg)
    slack_util.reply(slack, msg, response)