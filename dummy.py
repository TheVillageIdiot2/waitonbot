import time
import channel_util

msg = {
    "type": "message",
    "channel": channel_util.COMMAND_CENTER_ID,
    "user": "U0Q1PKL92",
    "text": "my name",
    "ts": "1355517523.000005"
}


class FakeClient(object):
    def rtm_send_message(self, channel=None, message="", thread=None, to_channel=None):
        print("Sent \"{}\" to channel {}".format(message, channel))

    def rtm_connect(self, with_team_state=None, auto_reconnect=None):
        return True

    def rtm_read(self):
        time.sleep(4)
        return [msg]
