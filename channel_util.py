
import shelve

DB_NAME = "channel_priveleges"

# Define our patterns
channel_check_pattern = r"channel id"
# channel_check_pattern = r"channel id <#(.*)>"
# identify_other_pattern = r"<@(.*)>\s+has scroll\s+(.*)"


def channel_check_callback(slack, msg, match):
    # Sets the users scroll
    # with shelve.open(DB_NAME) as db:

    # Respond
    slack_util.reply(slack, msg, msg["channel"])