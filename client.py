from __future__ import annotations

import asyncio
import json
import sys
import traceback
from typing import List, Any, AsyncGenerator, Dict, Coroutine, TypeVar
from typing import Optional

from aiohttp import web
from slackclient import SlackClient

import hooks
import slack_util

# Enable to do single-threaded and have better exceptions
DEBUG_MODE = False

"""
Objects to wrap slack connections
"""
# Read the API token


api_file = open("apitoken.txt", 'r')
SLACK_API = next(api_file).strip()
api_file.close()


class ClientWrapper(object):
    """
    Essentially the main state object.
    We only ever expect one of these per api token.
    Holds a slack client, and handles messsages.
    """

    def __init__(self, api_token):
        # Init slack
        self.slack = SlackClient(api_token)

        # Hooks go regex -> callback on (slack, msg, match)
        self.hooks: List[hooks.AbsHook] = []

        # Periodicals are just wrappers around an iterable, basically
        self.passives: List[hooks.Passive] = []

        # Cache users and channels
        self.users: Dict[str, slack_util.User] = {}
        self.conversations: Dict[str, slack_util.Conversation] = {}

    # Scheduled/passive events handling
    def add_passive(self, per: hooks.Passive) -> None:
        self.passives.append(per)

    async def run_passives(self) -> None:
        """
        Run all currently added passives
        """
        awaitables = [p.run() for p in self.passives]
        await asyncio.gather(*awaitables)

    # Incoming slack hook handling
    def add_hook(self, hook: hooks.AbsHook) -> None:
        self.hooks.append(hook)

    async def handle_events(self) -> None:
        """
        Asynchronous tasks that eternally reads and responds to messages.
        """
        # Create a queue
        queue = asyncio.Queue()

        # Create a task to put rtm events to the queue
        rtm_task = asyncio.create_task(self.rtm_event_feed(queue))

        # Create a task to put http events to the queue
        http_task = asyncio.create_task(self.http_event_feed(queue))

        # Create a task to handle all other tasks
        async def handle_task_loop():
            async for t3 in self.spool_tasks(queue):
                sys.stdout.flush()
                if DEBUG_MODE:
                    await t3

        # Handle them all
        await asyncio.gather(rtm_task, http_task, handle_task_loop())

    async def rtm_event_feed(self, msg_queue: asyncio.Queue) -> None:
        """
        Async wrapper around the message feed.
        Yields messages awaitably forever.
        """
        # Create the msg feed
        feed = slack_util.message_stream(self.slack)

        # Create a simple callable that gets one message from the feed
        def get_one():
            return next(feed)

        # Continuously yield async threaded tasks that poll the feed
        while True:
            next_event = await asyncio.get_running_loop().run_in_executor(None, get_one)
            await msg_queue.put(next_event)

    async def http_event_feed(self, event_queue: asyncio.Queue) -> None:
        # Create a callback to convert requests to events
        async def interr(request: web.Request):
            if request.can_read_body:
                # Get the payload
                post_params = await request.post()
                payload = json.loads(post_params["payload"])
                print("Interaction received: {}".format(payload))

                # Handle each action separately
                if "actions" in payload:
                    for action in payload["actions"]:
                        # Start building the event
                        ev = slack_util.Event()

                        # Get the user who clicked the button
                        ev.user = slack_util.UserContext(payload["user"]["id"])

                        # Get the channel it was clicked in
                        ev.conversation = slack_util.ConversationContext(payload["channel"]["id"])

                        # Get the message this button/action was attached to
                        ev.interaction = slack_util.InteractiveContext(payload["response_url"],
                                                                       payload["trigger_id"],
                                                                       action["block_id"],
                                                                       action["action_id"],
                                                                       action.get("value"))

                        # Put it in the queue
                        await event_queue.put(ev)

                # Respond that everything is fine
                return web.Response(status=200)
            else:
                # If we can't read it, get mad
                return web.Response(status=400)

        # Create the server
        app = web.Application()
        app.add_routes([web.post('/bothttpcallback', interr)])

        # Asynchronously serve that boy up
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, port=31019)
        await site.start()
        print("Server up")
        # while True:
        #     await asyncio.sleep(30)

    async def spool_tasks(self, event_queue: asyncio.Queue) -> AsyncGenerator[asyncio.Task, Any]:
        """
        Read in from async event feed, and spool them out as async tasks
        """
        while True:
            event: slack_util.Event = await event_queue.get()
            # Find which hook, if any, satisfies
            for hook in list(self.hooks):  # Note that we do list(self.hooks) to avoid edit-while-iterating issues
                # Try invoking each
                try:
                    # Try to make a coroutine handling the message
                    coro = hook.try_apply(event)

                    # If we get a coro back, then task it up and set consumption appropriately
                    if coro is not None:
                        print("Spawned task. Now {} running total.".format(len(asyncio.all_tasks())))
                        yield asyncio.create_task(_exception_printing_task(coro))
                        if hook.consumes:
                            break

                except hooks.HookDeath:
                    # If a hook wants to die, let it.
                    self.hooks.remove(hook)

    # Data getting/sending

    def get_conversation(self, conversation_id: str) -> Optional[slack_util.Conversation]:
        return self.conversations.get(conversation_id)

    def get_conversation_by_name(self, conversation_identifier: str) -> Optional[slack_util.Conversation]:
        # If looking for a direct message, first lookup user, then fetch
        if conversation_identifier[0] == "@":
            user_name = conversation_identifier

            # Find the user by their name
            raise NotImplementedError("There wasn't a clear use case for this yet, so we've opted to just not use it")

        # If looking for a channel, just lookup normally
        elif conversation_identifier[0] == "#":
            channel_name = conversation_identifier

            # Find the channel in the dict
            for channel in self.conversations.values():
                if channel.name == channel_name:
                    return channel

        # If it doesn't fit the above, we don't know how to process
        else:
            raise ValueError("Please give either an #channel-name or @user-name")

        # If we haven't returned already, give up and return None
        return None

    def get_user(self, user_id: str) -> Optional[slack_util.User]:
        return self.users.get(user_id)

    def get_user_by_name(self, user_name: str) -> Optional[slack_util.User]:
        raise NotImplementedError()

    def api_call(self, api_method, **kwargs):
        return self.slack.api_call(api_method, **kwargs)

    # Simpler wrappers around message sending/replying

    def reply(self, event: slack_util.Event, text: str, in_thread: bool = True) -> dict:
        """
        Replies to a message.
        Message must have a channel and message context.
        Returns the JSON response.
        """
        # Ensure we're actually replying to a valid message
        assert (event.conversation and event.message) is not None

        # Send in a thread by default
        if in_thread:
            # Figure otu what thread to send it to
            thread = event.message.ts
            if event.thread:
                thread = event.thread.thread_ts
            return self.send_message(text, event.conversation.conversation_id, thread=thread)
        else:
            return self.send_message(text, event.conversation.conversation_id)

    def _send_core(self, api_method: str, text: str, channel_id: str, thread: str, broadcast: bool,
                   blocks: List[dict]) -> dict:
        """
        Copy of the internal send message function of slack, with some helpful options.
        Returns the JSON response.
        """
        kwargs = {"channel": channel_id, "text": text}
        if thread:
            kwargs["thread_ts"] = thread
            if broadcast:
                kwargs["reply_broadcast"] = True
        if blocks:
            kwargs["blocks"] = blocks

        return self.api_call(api_method, **kwargs)

    def send_message(self,
                     text: str,
                     channel_id: str,
                     thread: str = None,
                     broadcast: bool = False,
                     blocks: List[dict] = None) -> dict:
        """
        Wraps _send_core for normal messages
        """
        return self._send_core("chat.postMessage", text, channel_id, thread, broadcast, blocks)

    def send_ephemeral(self,
                       text: str,
                       channel_id: str,
                       thread: str = None,
                       blocks: List[dict] = None) -> dict:
        """
        Wraps _send_core for ephemeral messages
        """
        return self._send_core("chat.postEphemeral", text, channel_id, thread, False, blocks)

    # Update slack data

    def update_channels(self):
        """
        Queries the slack API for all current channels
        """
        # Necessary because of pagination
        cursor = None

        # Make a new dict to use
        new_dict = {}

        # Iterate over results
        while True:
            # Set args depending on if a cursor exists
            args = {"limit": 1000, "types": "public_channel,private_channel,mpim,im"}
            if cursor:
                args["cursor"] = cursor

            channel_dicts = self.api_call("conversations.list", **args)

            # If the response is good, put its results to the dict
            if channel_dicts["ok"]:
                for channel_dict in channel_dicts["channels"]:
                    if channel_dict["is_im"]:
                        new_channel = slack_util.DirectMessage(id=channel_dict["id"],
                                                               user_id="@" + channel_dict["user"])
                    else:
                        new_channel = slack_util.Channel(id=channel_dict["id"],
                                                         name="#" + channel_dict["name"])
                    new_dict[new_channel.id] = new_channel

                # Fetch the cursor
                cursor = channel_dicts.get("response_metadata").get("next_cursor")

                # If cursor is blank, we're done new channels, just give it up
                if cursor == "":
                    break

            else:
                print("Warning: failed to retrieve channels. Message: {}".format(channel_dicts))
                break
        self.conversations = new_dict

    def update_users(self):
        """
        Queries the slack API for all current users
        """
        # Necessary because of pagination
        cursor = None

        while True:
            # Set args depending on if a cursor exists
            args = {"limit": 1000}
            if cursor:
                args["cursor"] = cursor

            user_dicts = self.api_call("users.list", **args)

            # Make a new dict to use
            new_dict = {}

            # If the response is good:
            if user_dicts["ok"]:
                for user_dict in user_dicts["members"]:
                    new_user = slack_util.User(id=user_dict.get("id"),
                                               name=user_dict.get("name"),
                                               real_name=user_dict.get("real_name"),
                                               email=user_dict.get("profile").get("email"))
                    new_dict[new_user.id] = new_user

                # Fetch the cursor
                cursor = user_dicts.get("response_metadata").get("next_cursor")

                # If cursor is blank, we're done new channels, just give it up
                if cursor == "":
                    break

            else:
                print("Warning: failed to retrieve users")
                break
        self.users = new_dict


# Create a single instance of the client wrapper
_singleton = ClientWrapper(SLACK_API)


def get_slack() -> ClientWrapper:
    return _singleton


"""
Miscellania
"""

A, B, C = TypeVar("A"), TypeVar("B"), TypeVar("C")


# Prints exceptions instead of silently dropping them in async tasks
async def _exception_printing_task(c: Coroutine[A, B, C]) -> Coroutine[A, B, C]:
    # Print exceptions as they pass through
    try:
        return await c
    except Exception:
        traceback.print_exc()
        raise
