"""
This file contains util for scroll polling
Only really kept separate for neatness sake.
"""

import re
from SlackUtil import reply
from fuzzywuzzy import fuzz
from fuzzywuzzy import process


#load the family tree
familyfile = open("sortedfamilytree.txt", 'r')

#Parse out 
p = re.compile("([0-9]*): (.*)$")
brothers = [p.match(line) for line in familyfile]
brothers = [m for m in brothers if m]
brothers = [{
        "scroll": int(m.group(1)),
        "name": m.group(2)
        } for m in brothers]


"""
Attempts to look up a user by scroll
"""
def handleScrollMsg(slack, msg):
    #Initialize response
    response = None

    #Get text
    text = msg['text']

    p = re.compile("scroll\\s*(.*?)$")
    m = p.match(text)
    if not m:
        response = "Could not parse your query. Please invoke as \"scroll <name>\" or \"scroll <scroll#>\""
    else:
        response = getResponseByQuery()

    reply(slack, msg, response, username="scrollbot")
  
def getResponseByQuery(query):
    try:
        #Try get scroll number
        scroll = int(m.group(1).strip())
        b = findBrotherByScroll(scroll)

        if b:
            return "Brother {0} has scroll {1}".format(b["name"], b["scroll"])
        else:
            return "Could not find scroll {0}".format(scroll)
    except ValueError:
        #Use as name
        name = m.group(1).strip()
        b = findBrotherByName(name)

        if b:
            return "Best match:\nBrother {0} has scroll {1}".format(b["name"], b["scroll"])
        else:
            return "Could not find brother {0}".format(name)
            

def findBrotherByScroll(scroll):
    for b in brothers:
        if b["scroll"] == scroll:
            return b
    return None

def findBrotherByName(name):
    #Try direct lookup
    """
    for b in brothers:
        if name.toLower() in b["name"].toLower():
            return b
    """

    #Do fuzzy match
    return process.extractOne(name, brothers, processor=lambda b: b["name"])
    
