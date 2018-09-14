"""
Allows users to register their user account as a specific scroll
"""

import shelve

import slack_util
import scroll_util

# The following db maps SLACK_USER_ID -> SCROLL_INTEGER
DB_NAME = "user_scrolls"

# Initialize the hooks
NON_REG_MSG = ("You currently have no scroll registered. To register, type\n"
               "i am 666\n"
               "except with your scroll instead of 666")


def identify_callback(slack, msg, match):
    # Sets the users scroll
    with shelve.open(DB_NAME) as db:
        # Get the query
        query = match.group(1).strip()

        try:
            user = msg.get("user")
            scroll = int(query)
            db[user] = scroll
            result = "Updated user {} to have scroll {}".format(user, scroll)
        except ValueError:
            result = "Bad scroll: {}".format(query)

        # Respond
        slack_util.reply(slack, msg, result)


def identify_other_callback(slack, msg, match):
    # Sets the users scroll
    with shelve.open(DB_NAME) as db:
        # Get the query
        user = match.group(1).strip()
        scroll_txt = match.group(2).strip()

        try:
            scroll = int(scroll_txt)
            if user in db:
                result = "To prevent trolling, once a users id has been set only they can change it"
            else:
                db[user] = scroll
                result = "Updated user {} to have scroll {}".format(user, scroll)
        except ValueError:
            result = "Bad scroll: {}".format(scroll_txt)

        # Respond
        slack_util.reply(slack, msg, result)


# noinspection PyUnusedLocal
def check_callback(slack, msg, match):
    # Tells the user their current scroll
    with shelve.open(DB_NAME) as db:
        try:
            scroll = db[msg.get("user")]
            result = "You are currently registered with scroll {}".format(scroll)
        except KeyError:
            result = NON_REG_MSG
        slack_util.reply(slack, msg, result)


# noinspection PyUnusedLocal
def name_callback(slack, msg, match):
    # Tells the user what slack thinks their name is
    with shelve.open(DB_NAME) as db:
        try:
            scroll = db[msg.get("user")]
            brother = scroll_util.find_by_scroll(scroll)
            if brother:
                result = "The bot thinks your name is {}".format(brother["name"])
            else:
                result = "The bot couldn't find a name for scroll {}".format(scroll)
        except (KeyError, ValueError):
            result = NON_REG_MSG

        # Respond
        slack_util.reply(slack, msg, result)


def lookup_msg_brother(msg):
    """
    Finds the real-world name of whoever posted msg.
    :return: brother dict or None
    """
    return lookup_slackid_brother(msg.get("user"))


def lookup_slackid_brother(slack_id):
    """
    Gets whatever brother the userid is registered to
    :return: Brother dict or None
    """
    with shelve.open(DB_NAME) as db:
        try:
            scroll = db[slack_id]
            return scroll_util.find_by_scroll(scroll)
        except ValueError:
            return None


def lookup_brother_userids(brother):
    """
    Returns a list of all userids associated with the given brother.
    :param brother: Std brother dict as specc'd in scroll_util
    :return: List of user id strings (may be empty)
    """
    with shelve.open(DB_NAME) as db:
        keys = db.keys()
        result = []
        for user_id in keys:
            if db[user_id] == brother["scroll"]:
                result.append(user_id)

        return result


identify_hook = slack_util.Hook(identify_callback, pattern=r"i am (.*)")
identify_other_hook = slack_util.Hook(identify_other_callback, pattern=r"<@(.*)>\s+has scroll\s+(.*)")
check_hook = slack_util.Hook(check_callback, pattern=r"my scroll")
name_hook = slack_util.Hook(name_callback, pattern=r"my name")
