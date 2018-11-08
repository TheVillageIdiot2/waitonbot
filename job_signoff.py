from typing import List, Any, Match, Tuple

from fuzzywuzzy import process
from slackclient import SlackClient

import channel_util
import google_api
import identifier
import job_nagger
import slack_util
import scroll_util

SHEET_ID = "1lPj9GjB00BuIq9GelOWh5GmiGsheLlowPnHLnWBvMOM"

# Note: These ranges use named range feature of google sheets.
# To edit range of jobs, edit the named range in Data -> Named Ranges in the Goole Sheets page
output_range = "JobScoreTrackerV2"

MIN_RATIO = 0.9
SIGNOFF_REWARD = 0.1


def get_curr_points() -> List[Tuple[str, float, str]]:
    """
    :return: The current contents of the output range
    """
    # Get the current stuff
    curr_output = google_api.get_sheet_range(SHEET_ID, output_range)
    all_jobs = job_nagger.get_jobs()

    # Each element: force length of 3. Fmt name, score, job
    def row_fixer(r: List[Any]) -> Tuple[str, float, str]:
        if len(r) == 0:
            return "", 0, "No Job"
        else:
            # Get the appropriate score
            if len(r) > 1:
                try:
                    curr_score = float(r[1])
                except ValueError:
                    curr_score = 0
            else:
                curr_score = 0

            # Find the current job
            job = "No Job"
            for j in all_jobs:
                if j.brother_name == r[0]:
                    job = "{} ({} - {})".format(j.job_name, j.day, j.house)
                    break
            return r[0], curr_score, job

    # Fix each row
    curr_output = [row_fixer(x) for x in curr_output]

    # Cut off the chaff - doesn't seem to be necessary.
    return curr_output


def put_points(vals: List[Tuple[str, float, str]]) -> None:
    # Turn the tuples to lists
    vals = [list(row) for row in vals]
    google_api.set_sheet_range(SHEET_ID, output_range, vals)


def alert_user(slack: SlackClient, name: str, saywhat: str) -> None:
    """
    DM a brother saying something
    """
    brother_dict = scroll_util.find_by_name(name)
    # We do this as a for loop just in case multiple people reg. to same scroll for some reason (e.g. dup accounts)
    for slack_id in identifier.lookup_brother_userids(brother_dict):
        dm_id = slack_util.im_channel_for_id(slack, slack_id)
        if dm_id:
            # Give a dummy msg dict, since we won't actually be using anything in it
            slack_util.reply(slack, {}, saywhat, to_channel=dm_id, in_thread=False)
        else:
            print("Warning: unable to find dm for brother {}".format(brother_dict))


async def signoff_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    """
    Callback to signoff a user.
    """
    # Find the index of our person.
    name = match.group(1)

    # Also, who just signed us off?
    signer = identifier.lookup_msg_brother(msg).name

    # Try giving the person a point
    try:
        (bro_name, bro_total, bro_job), (ass_name, ass_total, _) = adjust_scores((name, 1), (signer, SIGNOFF_REWARD))
        slack_util.reply(slack, msg, "Gave {} one housejob point for job {}.\n"
                                     "They now have {} for this period.\n"
                                     "You ({}) were credited with the signoff".format(bro_name, bro_job, bro_total, ass_name))
        alert_user(slack, bro_name,
                   "You, who we believe to be {}, just had your house job signed off by {}!".format(bro_name, ass_name))
    except scroll_util.BadName as e:
        # We didn't find a name - no action was performed.
        slack_util.reply(slack, msg, e.as_response())


async def punish_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    """
    Undoes a signoff. Maybe should rename
    """
    # Find the index of our person.
    name = match.group(2)

    # Also, who just signed us off?
    signer = identifier.lookup_msg_brother(msg).name

    # Try giving the person a point
    try:
        (bro_name, bro_total, _), (ass_name, ass_total, _) = adjust_scores((name, -1), (signer, -SIGNOFF_REWARD))
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

    except scroll_util.BadName as e:
        # We didn't find a name - no action was performed.
        slack_util.reply(slack, msg, e.as_response())


# noinspection PyUnusedLocal
async def reset_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    """
    Resets the scores.
    """
    # Get curr rows
    points = get_curr_points()

    new_points = [(a, 0, c) for a, _, c in points]
    put_points(new_points)
    slack_util.reply(slack, msg, "Reset scores")


def adjust_scores(*name_delta_tuples: Tuple[str, float]) -> List[Tuple[str, float, str]]:
    """
    Helper that uses a sequence of tuples in the format (name, delta) to adjust each (name) to have +delta score.
    Operation performed as a batch.
    :param name_delta_tuples: The name + score deltas
    :return: The updated tuples rows.
    """
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
            raise scroll_util.BadName(target_name, ratio, MIN_RATIO)

        # Where is he in the list?
        target_index = names.index(target_name)

        # Get his current score
        curr_score = points[target_index][1]
        curr_job = points[target_index][2]

        # target should be in the form index, (name, score)
        target_new = target_name, curr_score + delta, curr_job

        # Put it back
        points[target_index] = target_new

        # Record where we edited
        modified_user_indexes.append(target_index)

    # Push all to sheets if exit loop without error
    put_points(points)

    # Conver indexes to rows, then return the adjusted name/score_tuples
    return [points[i] for i in modified_user_indexes]


signoff_hook = slack_util.Hook(signoff_callback,
                               pattern=r"signoff\s+(.*)",
                               channel_whitelist=[channel_util.HOUSEJOBS])
undosignoff_hook = slack_util.Hook(punish_callback,
                                   pattern=r"(unsignoff|undosignoff|undo)\s+(.*)",
                                   channel_whitelist=[channel_util.HOUSEJOBS])
reset_hook = slack_util.Hook(reset_callback,
                             pattern=r"reset signoffs",
                             channel_whitelist=[channel_util.COMMAND_CENTER_ID])
