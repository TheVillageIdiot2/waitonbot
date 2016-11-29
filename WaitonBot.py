import GoogleApi as google#For read drive
from slackclient import SlackClient#Obvious
from SlackUtil import *

from WaitonUtil import handleWaitonMsg #For waitons
from ScrollUtil import handleScrollMsg #For scrolls
from TrueScrollUtil import handleTrueScrollMsg #For true scrolls
from kong import handleKongMsg
import re

#Read api token from file
apifile = open("apitoken.txt", 'r')
SLACK_API = next(apifile).strip()
apifile.close();

#Read killswitch from file
killswitchfile = open("killswitch.txt", 'r')
killswitch = next(killswitchfile).strip()
killswitchfile.close()

#Set default username.

#Authenticate, get sheets service. Done globally so we dont have to do this
#every fucking time, which is probably a bad idea
sheet_credentials = google.get_sheets_credentials()
sheet_service = google.get_sheets_service(sheet_credentials)

   
"""
Insults the scrub who tried to use the bot without setting up slack.
If for_user is supplied, assumes user was fine and insults for_user

Also provides helpful info for  how to avoid future disgrace, but thats like, tertiary
"""
def handleProfilelessScum(slack, msg, user, for_user=None):
    f_response = None
    if for_user:
        user_name = user['user']['name']
        for_name = for_user['user']['name']
        f_response = "Hey {0}, tell {1} to set up his fucking profile. Like, first and last name, and stuff".format(user_name, for_name)
    else:
        f_response = "Set up your profile before talking to me, scum.\n\nThat is to say, fill out your first and last name in your slack user profile! Please use what would be on the waiton list (IE your proper name, not a nickname)."
    reply(slack, msg, f_response)
    

waiton_pattern = re.compile("^waiton")
scroll_pattern = re.compile("^scroll")
true_scroll_pattern = re.compile("^truescroll")
housejob_pattern = re.compile("^(house)?job")
kong_pattern = re.compile("^kong")
       
def main():
    #Init slack
    slack = SlackClient(SLACK_API)
    print(slack)

    slack.api_call("chat.postMessage", channel="@jacobhenry", text="I'm back baby!")

    feed = messageFeed(slack)
    for msg in feed:
        #Check not bot
        if isBotMessage(msg):
            print("Message skipped. Reason: bot")
            continue
           
        #get user info
        userid = msg['user']
        user = slack.api_call("users.info", user=userid)

        #If a mention is found, assign for_user
        for_user = getForUser(slack, msg)           
        
        #Handle Message
        text = msg['text'].lower()
        msg['text'] = text
        if not isValidProfile(user):#invalid profile
            print("Received profileless")
            handleProfilelessScum(slack, msg, user)  

        elif for_user and not isValidProfile(for_user):#invalid for_user profile
            print("Received for profileless")
            handleProfilelessScum(slack, msg, user, for_user)

        elif waiton_pattern.match(text):
            print("Received waiton from " + user['user']['name'])
            handleWaitonMsg(slack, sheet_service, msg, user, for_user)

        elif scroll_pattern.match(text):
            print("Received scroll from " + user['user']['name'])
            handleScrollMsg(slack, msg)

        elif true_scroll_pattern.match(text):
            print("Received true scroll from " + user['user']['name'])
            handleTrueScrollMsg(slack, msg)

        elif housejob_pattern.match(text):
            print("Received housejob from " + user['user']['name'])
            reply(slack, msg, "I cannot do that (yet)", username="sadbot")
            
        elif kong_pattern.match(text):
            print("Received kong from " + user['user']['name'])
            handleKongMsg(slack, msg)

        elif killswitch == msg['text'].lower():
            reply(slack, msg, "as you wish...", username="rip bot")
            break

        else:
            print("Message skipped. Reason: no command found")

#run main 
main()
