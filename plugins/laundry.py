from __future__ import annotations
from typing import List, Match, Callable, TypeVar, Optional, Iterable, Any, Coroutine
from threading import Lock, Thread
from typing import Optional
from plugins import identifier, scroll_util
import hooks
import client
import slack_util
import datetime

#Singleton to handle all laundry room info
class LaundryRoom(metaclass=SingletonMeta):
    #Format is ["Name", Scroll, timeStarted, cycleLength]
    D1 = []
    D2 = []
    D3 = []
    W1 = []
    W2 = []
    #Whether that has already been notified
    D1Not = False
    D2Not = False
    D3Not = False
    W1Not = False
    W2Not = False


    def __init__(self) -> None:
        pass

    def updateNotification(self, machine):
        if machine == 0:
            self.D1Not = True
        elif machine == 1:
            self.D2Not = True
        elif machine == 2:
            self.D3Not = True
        elif machine == 3:
            self.W1Not = True
        elif machine == 4:
            self.W2Not = True

    #Returns the person, scroll, and time remaining on their cycle
    async def check_occupany(self):
        now = datetime.datetime.now()

        D1Time = (now - (self.D1[2] + datetime.timedelta(minutes=self.D1[3]))).total_seconds()
        D1Info = (self.D1[0], self.D1[1], 0 if D1Time else int(D1Time/-60))

        D2Time = (now - (self.D2[2] + datetime.timedelta(minutes=self.D2[3]))).total_seconds()
        D2Info = (self.D2[0], self.D2[1], 0 if D2Time else int(D2Time/-60))

        D3Time = (now - (self.D3[2] + datetime.timedelta(minutes=self.D3[3]))).total_seconds()
        D3Info = (self.D3[0], self.D3[1], 0 if D3Time else int(D3Time/-60))

        W1Time = (now - (self.W1[2] + datetime.timedelta(minutes=self.W1[3]))).total_seconds()
        W1Info = (self.W1[0], self.W1[1], 0 if W1Time else int(W1Time/-60))

        W2Time = (now - (self.W2[2] + datetime.timedelta(minutes=self.W2[3]))).total_seconds()
        W2Info = (self.W2[0], self.W2[1], 0 if W2Time else int(W2Time/-60))

        return (D1Info, D2Info, D3Info, W1Info, W2Info)

    #Returns the normal occupancy info plus if they have been notified already
    async def check_occupany_not(self):
        now = datetime.datetime.now()

        D1Time = (now - (self.D1[2] + datetime.timedelta(minutes=self.D1[3]))).total_seconds()
        D1Info = (self.D1[0], self.D1[1], 0 if D1Time else int(D1Time/-60), self.D1Not)

        D2Time = (now - (self.D2[2] + datetime.timedelta(minutes=self.D2[3]))).total_seconds()
        D2Info = (self.D2[0], self.D2[1], 0 if D2Time else int(D2Time/-60), self.D2Not)

        D3Time = (now - (self.D3[2] + datetime.timedelta(minutes=self.D3[3]))).total_seconds()
        D3Info = (self.D3[0], self.D3[1], 0 if D3Time else int(D3Time/-60), self.D3Not)

        W1Time = (now - (self.W1[2] + datetime.timedelta(minutes=self.W1[3]))).total_seconds()
        W1Info = (self.W1[0], self.W1[1], 0 if W1Time else int(W1Time/-60), self.W1Not)

        W2Time = (now - (self.W2[2] + datetime.timedelta(minutes=self.W2[3]))).total_seconds()
        W2Info = (self.W2[0], self.W2[1], 0 if W2Time else int(W2Time/-60), self.W2Not)

        return (D1Info, D2Info, D3Info, W1Info, W2Info)

    #Starts the designated machine by assigning it the info
    def start_machine(self, machineNum, info):
        if machineNum == 1:
            self.D1 = info
            self.D1Not = False
        elif machineNum == 2:
            self.D2 = info
            self.D2Not = False
        elif machineNum == 3:
            self.D3 = info
            self.D3Not = False
        elif machineNum == 4:
            self.W1 = info
            self.W1Not = False
        elif machineNum == 5:
            self.W2 = info
            self.W2Not = False


class SingletonMeta(type):
    #This is a thread-safe implementation of Singleton. I found this on the internet
    _instance: Optional[LaundryRoom] = None
    _lock: Lock = Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__call__(*args, **kwargs)
        return cls._instance


#For checking the occupancy status of the laundry room
async def check_callback(event: slack_util.Event, match: Match) -> None:
    laundry = LaundryRoom()
    tempResult = "-     D1\nD2    W1\nD3    W2\nD1: {} minutes left\nD2: {} minutes left\nD3: {} minutes left\nW1: {} minutes left\nW2: {} minutes left"
    occupany = await laundry.check_occupany()
    result = tempResult.format(occupany[0], occupany[1], occupany[2], occupany[3], occupany[4])
    client.get_slack().reply(event, result)

#For starting a new load in a machine
async def start_callback(event: slack_util.Event, match: Match) -> None:
    verb = slack_util.VerboseWrapper(event)

    laundry = LaundryRoom()

    machine = match.group(1).strip()
    scroll = match.group(2).strip()
    timeRemaining = match.group(3).strip()

    brother = await verb(scroll_util.find_by_scroll(scroll))

    info = [brother, int(scroll), datetime.datetime.now(), int(timeRemaining)]
    if machine[0].lower() == "w":
        if machine[1] == "1":
            laundry.start_machine(4, info)
        elif machine[1] == "2":
            laundry.start_machine(5, info)
        else:
            raise Exception("No other washers exist")
    elif machine[0].lower() == "d":
        if machine[1] == "1":
            laundry.start_machine(1, info)
        elif machine[1] == "2":
            laundry.start_machine(2, info)
        elif machine[1] == "3":
            laundry.start_machine(3, info)
        else:
            raise Exception("No other dryers exist")
    else:
        raise Exception("Only washers and dryers exist")

    result = "{} started by {} for {} minutes".format(machine, brother, timeRemaining)
    client.get_slack().reply(event, result)

#Help message for laundry related commands
async def help_callback(event: slack_util.Event, match: Match) -> None:
    message = "To start a laundry load type \"start w1 xxxx 50\" where w1 is the washer or dryer with number, xxxx is your scroll, and 50 is the minutes left on the machine\nTo check laundry room occupancy type \"check laundry\""
    client.get_slack().reply(event, message)

#Clear commands for clearing laundry
async def clear_callback(event: slack_util.Event, match: Match) -> None:
    info = []
    laundry = LaundryRoom()
    machine = match.group(1).strip()

    if machine[0].lower() == "w":
        if machine[1] == "1":
            laundry.start_machine(4, info)
        elif machine[1] == "2":
            laundry.start_machine(5, info)
        else:
            raise Exception("No other washers exist")
    elif machine[0].lower() == "d":
        if machine[1] == "1":
            laundry.start_machine(1, info)
        elif machine[1] == "2":
            laundry.start_machine(2, info)
        elif machine[1] == "3":
            laundry.start_machine(3, info)
        else:
            raise Exception("No other dryers exist")
    else:
        raise Exception("Only washers and dryers exist")

    message = "{} cleared".format(machine)
    client.get_slack().reply(event, message)

#TODO Remove whitelist once fully functional
check_hook = hooks.ChannelHook(check_callback, patterns=r"check laundry", channel_whitelist=["#botzone"])
start_hook = hooks.ChannelHook(start_callback, patterns=[r"start ([wW][12]) (/d{2,4}) (/d{1,2})", r"start ([dD][123]) (/d{2,4}) (/d{1,2})"], channel_whitelist=["#botzone"])
help_hook = hooks.ChannelHook(help_callback, patterns=r"help laundry", channel_whitelist=["#botzone"])
clear_hook = hooks.ChannelHook(clear_callback, patterns=[r"clear ([wW][12])", r"clear ([dD][123])"], channel_whitelist=["#botzone"])