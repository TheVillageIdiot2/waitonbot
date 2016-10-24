from slackclient import SlackClient


#One last call from beyond the grave
apifile = open("apitoken.txt", 'r')
SLACK_API = next(apifile).strip()
apifile.close();

slack = SlackClient(SLACK_API)
slack.api_call("chat.postMessage", channel="@jacobhenry", text="one error. and im die?")

