import threading
import re
from SlackUtil import reply
from time import sleep

DEFAULT_SONG = "dk_rap_classic"

#Patterns
patterns = {}
patterns['start'] = re.compile(r"#STARTSONG\s+(.*?)$")
patterns['time'] = re.compile(r"#TIMEPERLINE\s+(\d*)$")
patterns['rest'] = re.compile(r"#REST")
patterns['end'] = re.compile(r"#ENDSONG")

#SongContents
lyric_lines = []
f = open("lyrics.txt")
for line in f:
    lyric_lines += [line]
f.close()


class SongThread(threading.Thread):
    def __init__(self, callback, song_name):
        super().__init__()
        self.song_name = song_name
        self.callback = callback
        self.delay = 1000
        self.daemon = True
        
    def run(self):
        playing = False
        
        for line in lyric_lines:
            line = line.strip()
            if line == "":
                continue
               
            #Navigate to song start
            if not playing:
                m = patterns['start'].match(line)
                print(line)
                if m:
                    if m.group(1) == self.song_name:
                        playing = True
                        continue
            
            #Play loop
            else:
                #Config
                m = patterns['time'].match(line)
                if m:
                    self.delay = int(m.group(1))
                    continue

                #Rest line
                m = patterns['rest'].match(line)
                if m:
                    sleep(self.delay / 1000)
                    continue

                #End song
                m = patterns['end'].match(line)
                if m:
                    return
                    
                #"sing" line
                self.callback(line)
                sleep(self.delay / 1000)
                
        if not playing:
            self.callback("Could not find song")
            
def getAllTitles():
    titles = []
    for line in lyric_lines:
        m = patterns['start'].match(line)
        if m:
            titles += [m.group(1)]
            
    return titles
            
request_pattern = re.compile(r"kong\s*(.*?)$")
 
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
            st = SongThread(reply_callback, match.group(1))
            st.start()
        else:
            st = SongThread(reply_callback, DEFAULT_SONG)
            st.start()
    
    else:
        response = "Invoke as kong <songtitle:list>"
        reply_callback(response)

                
