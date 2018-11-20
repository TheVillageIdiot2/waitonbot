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


async def scroll_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    """
    Finds the scroll of a brother, or the brother of a scroll, based on msg text.
    """
    # Get the query
    query = match.group(1).strip()

    # Try to get as int or by name
    result = None
    try:
        sn = int(query)
        result = find_by_scroll(sn)
    except ValueError:
        try:
            result = await find_by_name(query)
        except BrotherNotFound:
            pass
    if result:
        result = "Brother {} has scroll {}".format(result.name, result.scroll)
    else:
        result = "Couldn't find brother {}".format(query)

    # Respond
    print(slack_util.reply(slack, msg, result))


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
class BrotherNotFound(Exception):
    """Throw when we can't find the desired brother."""
    pass


async def find_by_name(name: str, threshold: Optional[float] = None) -> Brother:
    """
    Looks up a brother by name. Raises exception if threshold provided and not met.

    :param threshold: Minimum match ratio to accept. Can be none.
    :param name: The name to look up, with a fuzzy search
    :raises BrotherNotFound:
    :return: The best-match brother
    """    # Get all of the names
    all_names = [b.name for b in brothers]

    # Do fuzzy match
    found, score = process.extractOne(name, all_names)
    score = score / 100.0
    found_index = all_names.index(found)
    found_brother = brothers[found_index]
    if (not threshold) or score > threshold:
        return found_brother
    else:
        msg = "Couldn't find brother {}. Best match \"{}\" matched with accuracy {}, falling short of safety minimum " \
              "accuracy {}. Please type name more accurately, to prevent misfires.".format(name,
                                                                                           found_brother,
                                                                                           score,
                                                                                           threshold)
        raise BrotherNotFound(msg)


scroll_hook = slack_util.Hook(scroll_callback, pattern=r"scroll\s+(.*)")
