import identifier
import scroll_util
import slack_util

nag_pattern = r"nag (.*)"


def nag_callback(slack, msg, match):
    # Get who we want to nag
    name = match.group(1)

    # Find them using scroll shit
    brother = scroll_util.find_by_name(name)

    # Get the associated user ids
    ids = identifier.lookup_brother_userids(brother)

    # Nag them each
    if ids:
        result = "Hey"
        for user_id in ids:
            result += " <@{}>".format(user_id)
            result += "!"
    else:
        result = "Nobody has identified themselves as {} ({})... Sad!".format(brother["name"], brother["scroll"])

    slack_util.reply(slack, msg, result, in_thread=False)
