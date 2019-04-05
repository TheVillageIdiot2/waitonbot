"""
Allows users to register their user account as a specific scroll
"""
import asyncio
import shelve
from typing import List, Match

import hooks
from plugins import scroll_util
import client
import slack_util

# The following db maps SLACK_USER_ID -> SCROLL_INTEGER
DB_NAME = "user_scrolls"
DB_LOCK = asyncio.Lock()

# Initialize the hooks
NON_REG_MSG = ("You currently have no scroll registered. To register, type\n"
               "i am 666\n"
               "except with your scroll instead of 666")


async def identify_callback(event: slack_util.Event, match: Match):
    """
    Sets the users scroll
    """
    async with DB_LOCK:
        with shelve.open(DB_NAME) as db:
            # Get the query
            query = match.group(1).strip()

            try:
                user = event.user.user_id
                scroll = int(query)
                db[user] = scroll
                result = "Updated user {} to have scroll {}".format(user, scroll)
            except ValueError:
                result = "Bad scroll: {}".format(query)

            # Respond
            client.get_slack().reply(event, result)


async def identify_other_callback(event: slack_util.Event, match: Match):
    """
    Sets another users scroll
    """
    async with DB_LOCK:
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
            client.get_slack().reply(event, result)


# noinspection PyUnusedLocal
async def check_callback(event: slack_util.Event, match: Match):
    """
    Replies with the users current scroll assignment
    """
    async with DB_LOCK:
        # Tells the user their current scroll
        with shelve.open(DB_NAME) as db:
            try:
                scroll = db[event.user.user_id]
                result = "You are currently registered with scroll {}".format(scroll)
            except KeyError:
                result = NON_REG_MSG
            client.get_slack().reply(event, result)


# noinspection PyUnusedLocal
async def name_callback(event: slack_util.Event, match: Match):
    """
    Tells the user what it thinks the calling users name is.
    """
    async with DB_LOCK:
        with shelve.open(DB_NAME) as db:
            try:
                scroll = db[event.user.user_id]
                brother = scroll_util.find_by_scroll(scroll)
                if brother:
                    result = "The bot thinks your name is {}".format(brother.name)
                else:
                    result = "The bot couldn't find a name for scroll {}".format(scroll)
            except (KeyError, ValueError):
                result = NON_REG_MSG

            # Respond
            client.get_slack().reply(event, result)


async def lookup_slackid_brother(slack_id: str) -> scroll_util.Brother:
    """
    Gets whatever brother the userid is registered to
    :raises BrotherNotFound:
    :return: Brother object or None
    """
    async with DB_LOCK:
        with shelve.open(DB_NAME) as db:
            try:
                scroll = db[slack_id]
                return scroll_util.find_by_scroll(scroll)
            except (KeyError, ValueError):
                raise scroll_util.BrotherNotFound("Slack id {} not tied to brother".format(slack_id))
    raise scroll_util.BrotherNotFound("Couldn't find an appropriate brother for slackid {}.".format(slack_id))


async def lookup_brother_userids(brother: scroll_util.Brother) -> List[str]:
    """
    Returns a list of all userids associated with the given brother.

    :param brother: Brother to lookup scrolls for
    :return: List of user id strings (may be empty)
    """
    async with DB_LOCK:
        with shelve.open(DB_NAME) as db:
            keys = db.keys()
            result = []
            for user_id in keys:
                if db[user_id] == brother.scroll:
                    result.append(user_id)

            return result


identify_hook = hooks.ChannelHook(identify_callback, patterns=r"my scroll is (.*)")
identify_other_hook = hooks.ChannelHook(identify_other_callback, patterns=r"<@(.*)>\s+has scroll\s+(.*)")
check_hook = hooks.ChannelHook(check_callback, patterns=r"what is my scroll")
name_hook = hooks.ChannelHook(name_callback, patterns=r"what is my name")
