#!/bin/bash

#This is just a basic loop to run in the background on my raspi.
#Restarts the bot if it dies, and notifies me

while :
do
  git pull
  echo "Press [CTRL+C] to stop..."
  sleep 1
  touch script_log.txt
  tail -n 1000 script_log.txt
  python3 WaitonBot.py &>> script_log.txt
  sleep 1
  echo "Died. Updating and restarting..."
done
