"""
This file handles conversion of users scrolls into numbers
"""

import re
from SlackUtil import reply

p = re.compile("truescroll\\s*(\d*)$")

def handleTrueScrollMsg(slack, msg):
    text = msg['text']
    response = None

    m = p.match(text)
    if not m:
        response = "Could not parse your query. Please invoke as \"truescroll <scroll#>\""
    else:
        num = m.group(1)
        brotherScroll = getBrotherScroll(num)
        trueScroll = getTrueScroll(num)

        response = "The brother with scroll {0} is in fact the {1} brother to sign\n"
        response += "The {2} brother to sign will have scroll {3}\n"

        response = response.format(num, trueScroll, num, brotherScroll)

    reply(slack, msg, response, username = "scrollbot")
        

brotherNums = [str(x) for x in range(10) if (not x == 3)]
trueNums    = [str(x) for x in range(10)]

def getTrueScroll(brotherScroll):
    return convertBase(brotherScroll, brotherNums, trueNums)


def getBrotherScroll(trueScroll):
    return convertBase(trueScroll, trueNums, brotherNums)
    

def convertBase(numStr, srcBaseNums, targBaseNums):
    #Returns int value
    def numberFromBase(ns, numerals):
        base = len(numerals)
        basePower = 1
        total = 0

        #Go by character.
        for c in ns[::-1]:
            try:
                digitVal = numerals.index(c)
                total += digitVal * basePower
            except ValueError:
                total += 0

            basePower = basePower * base

        return total

    #Returns string array, each elt is the corresponding numeral
    def numberToBase(n, numerals):
        if n==0:
            return [0]
        digits = []
        while n:
            digVal = int(n % len(numerals))
            digits.append(numerals[digVal])
            n /= len(numerals)
            n = int(n)
        return "".join(digits[::-1])

    return numberToBase(numberFromBase(numStr, srcBaseNums), targBaseNums)
