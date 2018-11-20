from dataclasses import dataclass
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

MIN_RATIO = 0.8


def alert_user(slack: SlackClient, brother: scroll_util.Brother, saywhat: str) -> None:
    """
    DM a brother saying something. Wrapper around several simpler methods
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


def tiemax(items: Iterable[T], key: Callable[[T], Optional[float]]) -> List[T]:
    best = []
    best_score = None
    for elt in items:
        # Compute the score
        score = key(elt)

        # Ignore blank scores
        if score is None:
            continue
        # Check if its the new best, wiping old if so
        elif best_score is None or score > best_score:
            best_score = score
            best = [elt]
        # Check if its same as last best
        elif score == best_score:
            best.append(elt)
    return best


@dataclass
class _ModJobContext:
    signer: scroll_util.Brother  # The brother invoking the command
    assign: house_management.JobAssignment  # The job assignment to modify


async def _mod_jobs(slack: SlackClient,
                    msg: dict,
                    relevance_scorer: Callable[[house_management.JobAssignment], Optional[float]],
                    modifier: Callable[[_ModJobContext], None],
                    no_job_msg: str = None
                    ) -> None:
    """
    Stub function that handles various tasks relating to modifying jobs
    :param relevance_scorer: Function scores job assignments on relevance. Determines which gets modified
    :param modifier: Callback function to modify a job. Only called on a successful operation, and only on one job
    """
    # Make an error wrapper
    verb = slack_util.VerboseWrapper(slack, msg)

    # Who invoked this command?
    signer = await verb(identifier.lookup_msg_brother(msg))

    # Get all of the assignments
    assigns = await verb(house_management.import_assignments())

    # Find closest assignment to what we're after. This just wraps relevance_scorer to handle nones.
    def none_scorer(a: Optional[house_management.JobAssignment]) -> Optional[float]:
        if a is None:
            return None
        else:
            return relevance_scorer(a)

    closest_assigns = tiemax(assigns, key=none_scorer)

    # This is what we do on success. It will or won't be called immediately based on what's in closest_assigns
    async def success_callback(targ_assign: house_management.JobAssignment) -> None:
        # First get the most up to date version of the jobs
        fresh_assigns = await verb(house_management.import_assignments())

        # Find the one that matches what we had before
        fresh_targ_assign = fresh_assigns[fresh_assigns.index(targ_assign)]

        # Create the context
        context = _ModJobContext(signer, fresh_targ_assign)

        # Modify it
        modifier(context)

        # Re-upload
        await house_management.export_assignments(fresh_assigns)

        # Also import and update points
        headers, points = await house_management.import_points()
        house_management.apply_house_points(points, fresh_assigns)
        house_management.export_points(headers, points)

    # If there aren't any jobs, say so
    if len(closest_assigns) == 0:
        if no_job_msg is None:
            no_job_msg = "Unable to find any jobs to apply this command to. Try again with better spelling or whatever."
        slack_util.reply(slack, msg, no_job_msg)

    # If theres only one job, sign it off
    elif len(closest_assigns) == 1:
        await success_callback(closest_assigns[0])

    # If theres multiple jobs, we need to get a follow up!
    else:
        # Say we need more info
        job_list = "\n".join("{}: {}".format(i, a.job.pretty_fmt()) for i, a in enumerate(closest_assigns))
        slack_util.reply(slack, msg, "Multiple relevant job listings found.\n"
                                     "Please enter the number corresponding to the job "
                                     "you wish to modify:\n{}".format(job_list))

        # Establish a follow up command pattern
        pattern = r"\d+"

        # Make the follow up callback
        async def foc(_slack: SlackClient, _msg: dict, _match: Match) -> None:
            # Get the number out
            index = int(_match.group(0))

            # Check that its valid
            if 0 <= index < len(closest_assigns):
                # We now know what we're trying to sign off!
                await success_callback(closest_assigns[index])
            else:
                # They gave a bad index, or we were unable to find the assignment again.
                slack_util.reply(_slack, _msg, "Invalid job index / job unable to be found.")

        # Make a listener hook
        new_hook = slack_util.ReplyWaiter(foc, pattern, msg["ts"], 120)

        # Register it
        client_wrapper.get_client_wrapper().add_hook(new_hook)


async def signoff_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    verb = slack_util.VerboseWrapper(slack, msg)

    # Find out who we are trying to sign off is
    signee_name = match.group(1)
    signee = await verb(scroll_util.find_by_name(signee_name, MIN_RATIO))

    # Score by name similarity, only accepting non-assigned jobs
    def scorer(assign: house_management.JobAssignment):
        r = fuzz.ratio(signee.name, assign.assignee.name)
        if assign.signer is None and r > MIN_RATIO:
            return r

    # Set the assigner, and notify
    def modifier(context: _ModJobContext):
        context.assign.signer = context.signer

        # Say we did it wooo!
        slack_util.reply(slack, msg, "Signed off {} for {}".format(context.assign.assignee.name,
                                                                   context.assign.job.name))
        alert_user(slack, context.assign.assignee, "{} signed you off for {}.".format(context.assign.signer.name,
                                                                                      context.assign.job.pretty_fmt()))

    # Fire it off
    await _mod_jobs(slack, msg, scorer, modifier)


async def late_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    verb = slack_util.VerboseWrapper(slack, msg)

    # Find out who we are trying to sign off is
    signee_name = match.group(1)
    signee = await verb(scroll_util.find_by_name(signee_name, MIN_RATIO))

    # Score by name similarity. Don't care if signed off or not
    def scorer(assign: house_management.JobAssignment):
        r = fuzz.ratio(signee.name, assign.assignee.name)
        if r > MIN_RATIO:
            return r

    # Just set the assigner
    def modifier(context: _ModJobContext):
        context.assign.late = not context.assign.late

        # Say we did it
        slack_util.reply(slack, msg, "Toggled lateness of {}.\n"
                                     "Now marked as late: {}".format(context.assign.job.pretty_fmt(),
                                                                     context.assign.late))

    # Fire it off
    await _mod_jobs(slack, msg, scorer, modifier)


async def reassign_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    verb = slack_util.VerboseWrapper(slack, msg)

    # Find out our two targets
    from_name = match.group(1).strip()
    to_name = match.group(2).strip()

    # Get them as brothers
    from_bro = await verb(scroll_util.find_by_name(from_name, MIN_RATIO))
    to_bro = await verb(scroll_util.find_by_name(to_name, MIN_RATIO))

    # Score by name similarity to the first brother. Don't care if signed off or not,
    # as we want to be able to transfer even after signoffs (why not, amirite?)
    def scorer(assign: house_management.JobAssignment):
        r = fuzz.ratio(from_bro.name, assign.assignee.name)
        if r > MIN_RATIO:
            return r

    # Change the assignee
    def modifier(context: _ModJobContext):
        context.assign.assignee = to_bro

        # Say we did it
        slack_util.reply(slack, msg, "Toggled lateness of {}.\n"
                                     "Now marked as late: {}".format(context.assign.job.pretty_fmt(),
                                                                     context.assign.late))

        # Tell the people
        reassign_msg = "Job {} reassigned from {} to {}".format(context.assign.job.pretty_fmt(),
                                                                from_bro,
                                                                to_bro)
        alert_user(slack, from_bro, reassign_msg)
        alert_user(slack, to_bro, reassign_msg)

    # Fire it off
    await _mod_jobs(slack, msg, scorer, modifier)


# noinspection PyUnusedLocal
async def reset_callback(slack: SlackClient, msg: dict, match: Match) -> None:
    """
    Resets the scores.
    """
    # Get curr rows
    headers, points = house_management.import_points()

    # Set to 0/default
    for i in range(len(points)):
        new = house_management.PointStatus(brother=points[i].brother)
        points[i] = new

    house_management.export_points(headers, points)

    # Now unsign everything
    assigns = await house_management.import_assignments()
    for a in assigns:
        if a is not None:
            a.signer = None
    await house_management.export_assignments(assigns)

    slack_util.reply(slack, msg, "Reset scores and signoffs")


async def nag_callback(slack, msg, match):
    # Get the day
    day = match.group(1).lower().strip()

    # Get the assigns
    assigns = await house_management.import_assignments()

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

late_hook = slack_util.Hook(late_callback,
                            pattern=r"marklate\s+(.*)",
                            channel_whitelist=[channel_util.HOUSEJOBS])

reset_hook = slack_util.Hook(reset_callback,
                             pattern=r"reset signoffs",
                             channel_whitelist=[channel_util.COMMAND_CENTER_ID])

nag_hook = slack_util.Hook(nag_callback,
                           pattern=r"nagjobs\s*(.*)",
                           channel_whitelist=[channel_util.COMMAND_CENTER_ID])

reassign_hook = slack_util.Hook(reassign_callback,
                                pattern=r"reassign\s+(.*?)\s+->\s+(.+)",
                                channel_whitelist=[channel_util.HOUSEJOBS])
