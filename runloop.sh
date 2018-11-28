#!/bin/bash

#This is just a basic loop to run in the background on my raspi.
#Restarts the bot if it dies, and notifies me

while :
do
  git pull
  echo "Press [CTRL+C] to stop..."
  sleep 1
  python3 -u main.py
  sleep 1
  echo "Died. Updating and restarting..."
done
