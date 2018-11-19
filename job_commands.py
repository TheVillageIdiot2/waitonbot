from typing import List, Match, Callable, TypeVar, Optional, Iterable

from fuzzywuzzy import fuzz
from slackclient import SlackClient

import channel_util
import client_wrapper
import house_management
import identifier
import scroll_util
import slack_util

SHEET_ID = "1lPj9GjB00BuIq9GelOWh5GmiGsheLlowPnHLnWBvMOM"

MIN_RATIO = 0.9


def alert_user(slack: SlackClient, brother: scroll_util.Brother, saywhat: str) -> None:
    """
    DM a brother saying something
    """
    # We do this as a for loop just in case multiple people reg. to same scroll for some reason (e.g. dup accounts)
    for slack_id in identifier.lookup_brother_userids(brother):
        dm_id = slack_util.im_channel_for_id(slack, slack_id)
        if dm_id:
            # Give a dummy msg dict, since we won't actually be using anything in it
            slack_util.send_message(slack, saywhat, dm_id)
        else:
            print("Warning: unable to find dm for brother {}".format(brother))


T = TypeVar("T")


def tiemax(items: Iterable[T], key: Callable[[T], float], min_score: Optional[float] = None) -> List[T]:
    best = []
    best_score = min_score
    for elt in items:
        score = key(elt)
        if best_score is None or score > best_score:
            best_score = score
            best = [elt]
        elif score == best_score:
            best.append(elt)
    return best


def do_signoff(slack: SlackClient, msg: dict, on_assign_index: int, by_brother: scroll_util.Brother) -> None:
    # First things first: Get the signoffs
    assignments = house_management.import_assignments()

    # Get the one we want
    on_assign = assignments[on_assign_index]

    # Modify it
    on_assign.signer = by_brother

    # Put them all back
    house_management.export_assignments(assignments)

    # Then we update points for house jobs
    headers, points = house_management.import_points()
    house_management.apply_house_points(points, assignments)
    house_management.export_points(headers, points)

    # Then we respond cool!
    slack_util.reply(slack, msg, "{} signed off {} for {}".format(on_assign.signer.name,
                                                                  on_assign.assignee.name,
                                                                  on_assign.job.pretty_fmt()))
    alert_user(slack, on_assign.assignee, "{} signed you off for {}.".format(on_assign.signer.name,
                                                                             on_assign.job.pretty_fmt()))


async def signoff_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    """
    Callback to signoff a user.
    """
    # Find out who this is
    signee_name = match.group(1)

    # Fix with a quick lookup
    try:
        signee = scroll_util.find_by_name(signee_name, MIN_RATIO, recent_only=True)
    except scroll_util.BadName as e:
        slack_util.reply(slack, msg, e.as_response())
        return

    # Also, who just signed us off?
    signer = identifier.lookup_msg_brother(msg)

    # Get all of the assignments
    assigns = house_management.import_assignments()

    # Find closest assignment to what we're after
    def scorer(a: Optional[house_management.JobAssignment]) -> float:
        if a is None:
            return 0
        else:
            return fuzz.ratio(signee.name, a.assignee.name)

    closest_assigns = tiemax(assigns, key=scorer)

    # Remove those that are already signed off
    closest_assigns = [c for c in closest_assigns if c is not None]
    closest_assigns = [c for c in closest_assigns if c.signer is None]

    # If there aren't any jobs, say so
    if len(closest_assigns) == 0:
        slack_util.reply(slack, msg, "Unable to find any jobs assigned to brother {} "
                                     "(identified as {}).".format(signee_name, signee.name))

    # If theres only one job, sign it off
    elif len(closest_assigns) == 1:
        targ_assign = closest_assigns[0]

        # Where is it?
        targ_assign_index = assigns.index(targ_assign)

        do_signoff(slack, msg, targ_assign_index, signer)

    # If theres multiple jobs, we need to get a follow up!
    else:
        # Say we need more info
        job_list = "\n".join("{}: {}".format(i, a.job.pretty_fmt()) for i, a in enumerate(closest_assigns))
        slack_util.reply(slack, msg, "Multiple sign off options dectected for brother {}.\n"
                                     "Please enter the number corresponding to the job you wish to "
                                     "sign off:\n{}\nIf you do not respond within 60 seconds, the signoff will "
                                     "expire.".format(signee_name, job_list))

        # Establish a follow up command pattern
        pattern = r"\d+"

        # Make the follow up callback
        async def foc(_slack: SlackClient, _msg: dict, _match: Match) -> None:
            # Get the number out
            index = int(_match.group(0))

            # Check that its valid
            if 0 <= index < len(closest_assigns):
                # We now know what we're trying to sign off!
                specific_targ_assign = closest_assigns[index]
                specific_targ_assign_index = assigns.index(specific_targ_assign)
                do_signoff(_slack, _msg, specific_targ_assign_index, signer)
            else:
                # They gave a bad index, or we were unable to find the assignment again.
                slack_util.reply(_slack, _msg, "Invalid job index / job unable to be found. Start over from the "
                                               "signoff step.")

        # Make a listener hook
        new_hook = slack_util.ReplyWaiter(foc, pattern, msg["ts"], 60)
        client_wrapper.get_client_wrapper().add_hook(new_hook)


# noinspection PyUnusedLocal
async def reset_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    """
    Resets the scores.
    """
    # Get curr rows
    headers, points = house_management.import_points()

    # Set to 0/default
    for i in range(len(points)):
        new = house_management.PointStatus(brother_raw=points[i].brother_raw, brother=points[i].brother)
        points[i] = new

    house_management.export_points(headers, points)

    # Now unsign everything
    assigns = house_management.import_assignments()
    for a in assigns:
        if a is not None:
            a.signer = None
    house_management.export_assignments(assigns)

    slack_util.reply(slack, msg, "Reset scores and signoffs")


async def nag_callback(slack, msg, match):
    # Get the day
    day = match.group(1).lower().strip()

    # Get the assigns
    assigns = house_management.import_assignments()

    # Filter to day
    assigns = [assign for assign in assigns if assign is not None and assign.job.day_of_week.lower() == day]

    # Filter signed off
    assigns = [assign for assign in assigns if assign.signer is None]

    # If no jobs found, somethings up. Probably mispelled day.
    if not assigns:
        slack_util.reply(slack, msg, "No jobs found. Check that the day is spelled correctly, with no extra symbols.\n"
                                     "It is possible that all jobs have been signed off, as well.",
                         in_thread=True)
        return

    # Nag each
    response = "Do yer jerbs! They are as follows:\n"
    for assign in assigns:
        # Make the row template
        response += "({}) {} -- {} ".format(assign.job.house, assign.job.name, assign.assignee.name)

        # Find the people to @
        brother_slack_ids = identifier.lookup_brother_userids(assign.assignee)

        if brother_slack_ids:
            for slack_id in brother_slack_ids:
                response += "<@{}> ".format(slack_id)
        else:
            response += "(scroll missing. Please register for @ pings!)"
        response += "\n"

    slack_util.reply(slack, msg, response, in_thread=False, to_channel=channel_util.GENERAL)


signoff_hook = slack_util.Hook(signoff_callback,
                               pattern=r"signoff\s+(.*)",
                               channel_whitelist=[channel_util.HOUSEJOBS])

reset_hook = slack_util.Hook(reset_callback,
                             pattern=r"reset signoffs",
                             channel_whitelist=[channel_util.COMMAND_CENTER_ID])

nag_hook = slack_util.Hook(nag_callback,
                           pattern=r"nagjobs\s*(.*)",
                           channel_whitelist=[channel_util.COMMAND_CENTER_ID])
