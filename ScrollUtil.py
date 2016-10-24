"""
This file contains util for scroll polling
Only really kept separate for neatness sake.
"""

import re
from SlackUtil import reply


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
        #Initially try to parse numeric
        try:
            #Try get scroll
            scroll = int(m.group(1).strip())

            for b in brothers:
                if b["scroll"] == scroll:
                    response = "Brother {0} has scroll {1}".format(b["name"], b["scroll"])
                    break

            #If response still none, say so
            response = response or "Could not find scroll {0}".format(scroll)

        except ValueError:
            #Use as name
            name = m.group(1).strip()

            for b in brothers:
                if name in b["name"]:
                    response = "Brother {0} has scroll {1}".format(b["name"], b["scroll"])
                    break

            #If response still none, say so
            response = response or "Could not find brother {0}".format(name)

    reply(slack, msg, response, username="scrollbot")
  
