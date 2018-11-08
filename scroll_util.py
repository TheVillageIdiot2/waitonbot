"""
This file contains util for scroll polling
Only really kept separate for neatness sake.
"""

import re
from typing import List, Optional, Match

from fuzzywuzzy import process
from slackclient import SlackClient

import slack_util


class Brother(object):
    """
    Represents a brother.
    """
    def __init__(self, name: str, scroll: int):
        self.name = name
        self.scroll = scroll


# load the family tree
familyfile = open("sortedfamilytree.txt", 'r')

# Parse out
brother_match = re.compile(r"([0-9]*)~(.*)")
brothers_matches = [brother_match.match(line) for line in familyfile]
brothers_matches = [m for m in brothers_matches if m]
brothers: List[Brother] = [Brother(m.group(2), int(m.group(1))) for m in brothers_matches]


async def scroll_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    """
    Finds the scroll of a brother, or the brother of a scroll, based on msg text.
    """
    # Get the query
    query = match.group(1).strip()

    # Try to get as int or by name
    try:
        sn = int(query)
        result = find_by_scroll(sn)
    except ValueError:
        result = find_by_name(query)
    if result:
        result = "Brother {} has scroll {}".format(result.name, result.scroll)
    else:
        result = "Couldn't find brother {}".format(query)

    # Respond
    slack_util.reply(slack, msg, result)


def find_by_scroll(scroll: int) -> Optional[Brother]:
    """
    Lookups a brother in the family list, using their scroll.

    :param scroll: The integer scroll to look up
    :return: The brother, or None
    """
    for b in brothers:
        if b.scroll == scroll:
            return b
    return None


# Used to track a sufficiently shitty typed name
class BadName(Exception):
    def __init__(self, name: str, score: float, threshold: float):
        self.name = name
        self.score = score
        self.threshold = threshold

    def as_response(self) -> str:
        return "Unable to perform operation. Best name match {} had a match score of {}, falling short of minimum " \
               "match ratio {}. Please type name better.".format(self.name, self.score, self.threshold)


def find_by_name(name: str, threshold: Optional[float] = None) -> Brother:
    """
    Looks up a brother by name. Raises exception if threshold provided and not met.

    :param threshold: Minimum match ratio to accept. Can be none.
    :param name: The name to look up, with a fuzzy search
    :return: The best-match brother
    """
    # Really quikly mog name into Brother, so the processor function works fine
    name_bro = Brother(name, -1)

    # Do fuzzy match
    found = process.extractOne(name_bro, brothers, processor=lambda b: b.name)
    if (not threshold) or found[1] > threshold:
        return found[0]
    else:
        raise BadName(name, found[1], threshold)


scroll_hook = slack_util.Hook(scroll_callback, pattern=r"scroll\s+(.*)")
