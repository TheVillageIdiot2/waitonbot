#!/bin/bash

#This is just a basic loop to run in the background on my raspi.
#Restarts the bot if it dies, and notifies me

while :
do
  echo "Press [CTRL+C] to stop..."
  sleep 5
  python3 WaitonBot.py
  sleep 1
  python3 CallOfTheVoid.py
done
