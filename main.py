import asyncio

import channel_util
import identifier
import job_commands
import management_commands
import periodicals
import scroll_util
import slavestothemachine

# Read api token from file
from client_wrapper import ClientWrapper


def main() -> None:
    wrap = ClientWrapper()

    # Add scroll handling
    wrap.add_hook(scroll_util.scroll_hook)

    # Add id handling
    wrap.add_hook(identifier.check_hook)
    wrap.add_hook(identifier.identify_hook)
    wrap.add_hook(identifier.identify_other_hook)
    wrap.add_hook(identifier.name_hook)

    # Added channel utility
    wrap.add_hook(channel_util.channel_check_hook)

    # Add nagging functionality
    wrap.add_hook(job_commands.nag_hook)

    # Add kill switch
    wrap.add_hook(management_commands.reboot_hook)

    # Add towel rolling
    wrap.add_hook(slavestothemachine.count_work_hook)
    wrap.add_hook(slavestothemachine.dump_work_hook)

    # Add signoffs
    wrap.add_hook(job_commands.signoff_hook)
    wrap.add_hook(job_commands.reset_hook)

    # Add help
    # help_callback = management_commands.list_hooks_callback_gen(wrap.hooks)
    # wrap.add_hook(slack_util.Hook(help_callback, pattern=management_commands.bot_help_pattern))

    # Add boozebot
    wrap.add_passive(periodicals.ItsTenPM())

    event_loop = asyncio.get_event_loop()
    event_loop.set_debug(True)
    message_handling = wrap.respond_messages()
    passive_handling = wrap.run_passives()
    both = asyncio.gather(message_handling, passive_handling)
    event_loop.run_until_complete(both)


# run main
if __name__ == '__main__':
    main()
