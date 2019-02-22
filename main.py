import asyncio
import textwrap
from typing import Match

import identifier
import job_commands
import management_commands
import periodicals
import scroll_util
import slack_util
import slavestothemachine


def main() -> None:
    wrap = slack_util.get_slack()

    # Add scroll handling
    wrap.add_hook(scroll_util.scroll_hook)

    # Add id handling
    wrap.add_hook(identifier.check_hook)
    wrap.add_hook(identifier.identify_hook)
    wrap.add_hook(identifier.identify_other_hook)
    wrap.add_hook(identifier.name_hook)

    # Add kill switch
    wrap.add_hook(management_commands.reboot_hook)

    # Add towel rolling
    wrap.add_hook(slavestothemachine.count_work_hook)
    # wrap.add_hook(slavestothemachine.dump_work_hook)

    # Add job management
    wrap.add_hook(job_commands.signoff_hook)
    wrap.add_hook(job_commands.late_hook)
    wrap.add_hook(job_commands.reset_hook)
    wrap.add_hook(job_commands.nag_hook)
    wrap.add_hook(job_commands.reassign_hook)
    wrap.add_hook(job_commands.refresh_hook)

    # Add help
    wrap.add_hook(slack_util.ChannelHook(help_callback, patterns=[r"help", r"bot\s+help"]))

    # Add boozebot
    # wrap.add_passive(periodicals.ItsTenPM())

    # Add automatic updating of users
    wrap.add_passive(periodicals.Updatinator(wrap, 60))

    # Add nagloop
    wrap.add_passive(periodicals.NotifyJobs())
    wrap.add_passive(periodicals.RemindJobs())

    event_loop = asyncio.get_event_loop()
    event_loop.set_debug(slack_util.DEBUG_MODE)
    message_handling = wrap.respond_messages()
    passive_handling = wrap.run_passives()
    both = asyncio.gather(message_handling, passive_handling)
    event_loop.run_until_complete(both)


# noinspection PyUnusedLocal
async def help_callback(event: slack_util.Event, match: Match) -> None:
    slack_util.get_slack().reply(event, textwrap.dedent("""
    Commands are as follows. Note that some only work in certain channels.
    "my scroll is number" : Registers your slack account to have a certain scroll, for the purpose of automatic dm's.
    "@person has scroll number" : same as above, but for other users. Helpful if they are being obstinate.
    "what is my scroll" : Echos back what the bot thinks your scroll is. Largely for debugging.
    "what is my name" : Echos back what the bot thinks your name is. Largely for debugging. If you want to change this, 
    you'll need to fix the "Sorted family tree" file that the bot reads. Sorry.
    "channel id #wherever" : Debug command to get a slack channels full ID
    "reboot" : Restarts the server.
    "signoff John Doe" : Sign off a brother's house job. Will prompt for more information if needed.
    "marklate John Doe" : Same as above, but to mark a job as being completed but having been done late.
    "reassign John Doe -> James Deer" : Reassign a house job.
    "undo signoff John Doe" : Marks a brother's house job as incomplete. Useful if you fucked up.
    "nagjobs day" : Notify in general the house jobs for the week.
    "reset signoffs" : Clear points for the week, and undo all signoffs. Not frequently useful, admin only.
    "refresh points" : Updates house job / signoff points for the week, after manual edits to the sheet. Admin only.
    "help" : You're reading it. This is all it does. What do you want from me?
    
    ---
    
    Also of note is that in #slavestothemachine, any wording of the format "replaced <number>", or similarly with 
    "washed", "dried", "rolled", or "flaked", will track your effort for the week.
    
    Github is https://github.com/TheVillageIdiot2/waitonbot
    Man in charge is Jacob Henry, but nothing lasts forever.
    """))
    # Do not let my efforts fall to waste. Its a pitious legacy but its something, at least, to maybe tide the
    # unending flow of work for poor Niko.

# run main
if __name__ == '__main__':
    main()
