"""
This file contains util for scroll polling
Only really kept separate for neatness sake.
"""

import re
from slack_util import reply
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

# load the family tree
familyfile = open("sortedfamilytree.txt", 'r')


command_pattern = r"scroll\s+(.*)"

# Parse out
brother_match = re.compile(r"([0-9]*)~(.*)")
brothers = [brother_match.match(line) for line in familyfile]
brothers = [m for m in brothers if m]
brothers = [{
    "scroll": int(m.group(1)),
    "name": m.group(2)
} for m in brothers]

"""
Attempts to look up a user by scroll
"""


def callback(slack, msg, match):
    # Get the query
    query = match.group(1).strip()

    # Try to get as int or by name
    try:
        sn = int(query)
        result = find_by_scroll(sn)
    except ValueError:
        result = find_by_name(query)
    if result:
        result = "Brother {} has scroll {}".format(result["name"], result["scroll"])
    else:
        result = "Couldn't find brother {}".format(query)

    # Respond
    reply(slack, msg, result)


def find_by_scroll(scroll):
    for b in brothers:
        if b["scroll"] == scroll:
            return b
    return None


def find_by_name(name):
    # coerce name into dict form
    name = {"name": name}

    # Do fuzzy match
    return process.extractOne(name, brothers, processor=lambda b: b["name"])[0]
