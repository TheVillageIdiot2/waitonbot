from time import sleep
import re #Regular expressions

"""
Slack helpers. Separated for compartmentalization
"""

DEFAULT_USERNAME = "cylon" #NICE MEME

"""
Sends message with "text" as its content to the channel that message came from
"""  
def reply(slack, msg, text, username=DEFAULT_USERNAME):
    channel = msg['channel']
    slack.api_call("chat.postMessage", channel=channel, text=text, username=username)


            
"""
Returns whether or not msg came from bot
"""
def isBotMessage(msg):
    return ("bot_id" in msg or "user" not in msg)
 
         
"""
Generator that yields messages from slack.
Messages are in standard api format, look it up.
Checks on 2 second intervals (may be changed)
"""
def messageFeed(slack):
    if slack.rtm_connect():
        print("Waiting for messages")
        while True:
            sleep(2)
            update = slack.rtm_read()
            for item in update:
                if item['type'] == 'message':
                    yield item
    
    print("Critical slack connection failure")
    return
    
 
"""
Returns whether or not user has configured profile
"""
def isValidProfile(user):
    return ('profile'       in user['user'] and
            'first_name'    in user['user']['profile'] and
            'last_name'     in user['user']['profile'])

    
"""
Gets the user info for whoever is first mentioned in the message, 
or None if no mention is made
"""
def getForUser(slack, msg):
    m_re = re.compile(".*?<@([A-Z0-9]*?)>")
    mention_match = m_re.match(msg['text'])
    if mention_match is not None:
        mention_id = mention_match.group(1)
        return slack.api_call("users.info", user=mention_id)
    else:
        return None
 
