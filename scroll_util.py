"""
This file contains util for scroll polling
Only really kept separate for neatness sake.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Match

from fuzzywuzzy import process
from slackclient import SlackClient

import slack_util

# Use this if we can't figure out who a brother actually is
MISSINGBRO_SCROLL = 0


@dataclass
class Brother(object):
    """
    Represents a brother.
    """
    name: str
    scroll: int


# load the family tree
familyfile = open("sortedfamilytree.txt", 'r')

# Parse out
brother_match = re.compile(r"([0-9]*)~(.*)")
brothers_matches = [brother_match.match(line) for line in familyfile]
brothers_matches = [m for m in brothers_matches if m]
brothers: List[Brother] = [Brother(m.group(2), int(m.group(1))) for m in brothers_matches]
recent_brothers: List[Brother] = brothers[700:]

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


def find_by_name(name: str, threshold: Optional[float] = None, recent_only: bool=False) -> Brother:
    """
    Looks up a brother by name. Raises exception if threshold provided and not met.

    :param threshold: Minimum match ratio to accept. Can be none.
    :param name: The name to look up, with a fuzzy search
    :param recent_only: Whether or not to only search more recent undergrad brothers.
    :return: The best-match brother
    """
    # Pick a list
    if recent_only:
        bros_to_use = recent_brothers
    else:
        bros_to_use = brothers

    # Get all of the names
    all_names = [b.name for b in bros_to_use]

    # Do fuzzy match
    found, score = process.extractOne(name, all_names)
    score = score / 100.0
    if (not threshold) or score > threshold:
        found_index = all_names.index(found)
        return bros_to_use[found_index]
    else:
        raise BadName(found, score, threshold)


scroll_hook = slack_util.Hook(scroll_callback, pattern=r"scroll\s+(.*)")
