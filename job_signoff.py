from fuzzywuzzy import process

import channel_util
import google_api
import identifier
import slack_util
import scroll_util

SHEET_ID = "1lPj9GjB00BuIq9GelOWh5GmiGsheLlowPnHLnWBvMOM"

# Note: These ranges use named range feature of google sheets.
# To edit range of jobs, edit the named range in Data -> Named Ranges in the Goole Sheets page
output_range = "JobScoreTracker"

MIN_RATIO = 0.9
SIGNOFF_REWARD = 0.1
SAFETY_DELAY = 5


# Used to track a sufficiently shitty typed name
class BadName(Exception):
    def __init__(self, name, score):
        self.name = name
        self.score = score

    def as_response(self):
        return "Unable to perform operation. Best name match {} had a match score of {}, falling short of match ratio " \
               "{}. Please type name better.".format(self.name, self.score, MIN_RATIO)


def get_curr_points():
    # Get the current stuff
    curr_output = google_api.get_sheet_range(SHEET_ID, output_range)

    # Each element: force length of 2.
    def row_fixer(r):
        if len(r) == 0:
            return ["", 0]
        elif len(r) == 1:
            return [r[0], 0]
        else:
            try:
                v = float(r[1])
            except ValueError:
                v = 0
            return [r[0], v]

    # Fix each row
    curr_output = [row_fixer(x) for x in curr_output]

    # Cut off the chaff - doesn't seem to be necessary.
    return curr_output


def put_points(vals):
    google_api.set_sheet_range(SHEET_ID, output_range, vals)


def signoff_callback(slack, msg, match):
    # Find the index of our person.
    name = match.group(1)

    # Also, who just signed us off?
    signer = identifier.lookup_msg_brother(msg)["name"]

    # Try giving the person a point
    try:
        (bro_name, bro_total), (ass_name, ass_total) = adjust_scores((name, 1), (signer, SIGNOFF_REWARD))
        slack_util.reply(slack, msg, "Gave {} one housejob point.\n"
                                     "They now have {} for this period.\n"
                                     "You ({}) were credited with the signoff".format(bro_name, bro_total, ass_name))
        alert_user(slack, bro_name,
                   "You, who we believe to be {}, just had your house job signed off by {}!".format(bro_name, ass_name))
    except BadName as e:
        # We didn't find a name - no action was performed.
        slack_util.reply(slack, msg, e.as_response())


def alert_user(slack, name, saywhat):
    """
    DM a brother saying something
    """
    brother_dict = scroll_util.find_by_name(name)
    # We do this as a for loop just in case multiple people reg. to same scroll for some reason (e.g. dup accounts)
    for slack_id in identifier.lookup_brother_userids(brother_dict):
        dm_id = slack_util.im_channel_for_id(slack, slack_id)
        if dm_id:
            slack_util.reply(slack, None, saywhat, to_channel=dm_id, in_thread=False)
        else:
            print("Warning: unable to find dm for brother {}".format(brother_dict))


def punish_callback(slack, msg, match):
    # Find the index of our person.
    name = match.group(2)

    # Also, who just signed us off?
    signer = identifier.lookup_msg_brother(msg)["name"]

    # Try giving the person a point
    try:
        (bro_name, bro_total), (ass_name, ass_total) = adjust_scores((name, -1), (signer, -SIGNOFF_REWARD))
        slack_util.reply(slack, msg, "Took one housejob point from {}.\n"
                                     "They now have {} for this period.\n"
                                     "Under the assumption that this was to undo a mistake, we have deducted the "
                                     "usual signoff reward from you, ({}).\n "
                                     "You can easily earn it back by signing off the right person ;).".format(bro_name,
                                                                                                              bro_total,
                                                                                                              ass_name))
        alert_user(slack, bro_name,
                   "You, who we believe to be {}, just had your house job UN-signed off by {}.\n"
                   "Perhaps the asshoman made a mistake when they first signed you off.\n"
                   "If you believe that they undid the signoff accidentally, go talk to them".format(bro_name, signer))

    except BadName as e:
        # We didn't find a name - no action was performed.
        slack_util.reply(slack, msg, e.as_response())


def adjust_scores(*name_delta_tuples):
    # Get the current stuff
    points = get_curr_points()
    names = [p[0] for p in points]
    modified_user_indexes = []

    for name, delta in name_delta_tuples:
        # Find our guy
        target_name, ratio = process.extractOne(name, names)
        ratio = ratio / 100.0

        # If bad ratio, error
        if ratio < MIN_RATIO:
            raise BadName(target_name, ratio)

        # Where is he in the list?
        target_index = names.index(target_name)

        # Get his current score
        curr_score = points[target_index][1]

        # target should be in the form index, (name, score)
        target_new = [target_name, curr_score + delta]

        # Put it back
        points[target_index] = target_new

        # Record where we edited
        modified_user_indexes.append(target_index)

    # Push all to sheets if exit loop without error
    put_points(points)

    # Conver indexes to rows, then return the adjusted name/score_tuples
    return [points[i] for i in modified_user_indexes]


def reset_callback(slack, msg, match):
    pass
    # reset_callback()


signoff_hook = slack_util.Hook(signoff_callback, pattern=r"signoff\s+(.*)",
                               channel_whitelist=[channel_util.HOUSEJOBS])
undosignoff_hook = slack_util.Hook(punish_callback, pattern=r"(unsignoff|undosignoff|undo)\s+(.*)",
                                   channel_whitelist=[channel_util.HOUSEJOBS])
# reset_hook = slack_util.Hook(reset_callback, pattern=r"reset_job_scores")
