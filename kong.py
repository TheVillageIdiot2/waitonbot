import threading
import re
from SlackUtil import reply
from time import sleep

DEFAULT_SONG = "dk_rap_classic"

#Patterns
patterns = {}
patterns['start'] = re.compile("^#STARTSONG (.*?)")
patterns['time'] = re.compile("^#TIMEPERLINE (\\d*)")
patterns['rest'] = re.compile("^#REST")
patterns['end'] = re.compile("^#ENDSONG")

#SongContents
lyric_lines = []
f = open("lyrics.txt")
for line in f:
    lyric_lines += [line]
f.close()


class SongThread(threading.Thread):
    def __init__(this, replycallback, song_name):
        this.slack = slack
        this.song_name = song_name
        this.song_lines = song_lines
        this.delay = 1000
        this.daemon = True
        
        
    def run(this):
        playing = False
        
        for line in lyric_lines:
            if line == "":
                continue
               
            #Navigate to song start
            if not playing:
                if m = patterns['start'].match(line):
                    if m.group(1) == this.song_name:
                        playing = True
                        continue
            
            #Play loop
            else:
                #Config
                if m = patterns['time'].match(line):
                    this.delay = int(m.group(1))
                
                #Rest line
                elif m = patterns['rest'].match(line):
                    sleep(this.delay / 1000)
                  
                #End song
                elif m = patterns['end'].match(line):
                    return
                    
                #"sing" line
                else:
                    replycallback(line)
                    sleep(this.delay / 1000)
                
        if not playing:
            replycallback("Could not find song")
            
def getAllTitles():
    titles = []
    for line in lyric_lines:
        m = patterns['start'].match(line)
        if m:
            titles += [m.group(1)]
            
    return titles
            
request_pattern = re.compile("kong (.*?)$")
 
def handleKongMsg(slack, msg):
    #Get text
    text = msg['text']
    match = request_pattern.match(text)
    
    #Make callback function
    reply_callback = lambda response: reply(slack, msg, response, username="jukebot")
    if match:
        if match.group(1) == "list":
            response = ""
            for title in getAllTitles():
                response = response + title
            reply_callback(response)
         
        elif match.group(1) != "":
            st = SongThread(reply_callback, m.group(1))
            st.start()
        else:
            st = SongThread(reply_callback, DEFAULT_SONG)
            st.start()
    
    else:
        response = "Invoke as kong <songtitle:list>"
        reply_callback(response)

                