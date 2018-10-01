import channel_util
import slack_util
import identifier
import re
import shelve

counted_data = ["flaked", "rolled", "replaced", "washed", "dried"]
lookup_format = "{}\s+(\d+)"

DB_NAME = "towels_rolled"


def fmt_work_dict(work_dict):
    return ",\n".join(["{} × {}".format(job, count) for job, count in sorted(work_dict.items())])


def count_work_callback(slack, msg, match):
    with shelve.open(DB_NAME) as db:
        text = msg["text"].lower().strip()

        # Couple things to work through.
        # One: Who sent the message?
        who_wrote = identifier.lookup_msg_brother(msg)
        who_wrote_label = "{} [{}]".format(who_wrote["name"], who_wrote["scroll"])

        # Two: What work did they do?
        new_work = {}
        for job in counted_data:
            pattern = lookup_format.format(job)
            match = re.search(pattern, text)
            if match:
                new_work[job] = int(match.group(1))

        # Three: check if we found anything
        if len(new_work) == 0:
            if re.search(r'\s\d\s', text) is not None:
                slack_util.reply(slack, msg, "No work recognized. Use words {} or work will not be recorded".format(counted_data))
            return

        # Three: Add it to their total work. We key by user_id, to avoid annoying identity shit
        db_key = msg["user"]
        old_work = db.get(db_key) or {}
        total_work = dict(old_work)

        for job, count in new_work.items():
            if job not in total_work:
                total_work[job] = 0
            total_work[job] += count

        # Save
        db[db_key] = total_work

        # Four, congratulate them on their work
        congrats = "{} recorded work:\n{}\nTotal work since last dump now\n{}".format(who_wrote_label,
                                                                                    fmt_work_dict(new_work),
                                                                                    fmt_work_dict(total_work))
        slack_util.reply(slack, msg, congrats)


def dump_work_callback(slack, msg, match):
    with shelve.open(DB_NAME) as db:
        # Dump out each user
        keys = db.keys()
        result = ["All work:"]
        for user_id in keys:
            # Get the work
            work = db[user_id]
            del db[user_id]

            # Get the name
            brother_name = identifier.lookup_slackid_brother(user_id)
            if brother_name is None:
                brother_name = user_id
            else:
                brother_name = brother_name["name"]

            result.append("{} has done:\n{}".format(brother_name, fmt_work_dict(work)))

        result.append("Database wiped. Next dump will show new work since the time of this message")
        # Send it back
        slack_util.reply(slack, msg, "\n".join(result))


# Make dem HOOKs
count_work_hook = slack_util.Hook(count_work_callback, channel_whitelist=[channel_util.SLAVES_TO_THE_MACHINE_ID])
dump_work_hook = slack_util.Hook(dump_work_callback, pattern="dump towel data", channel_whitelist=[channel_util.COMMAND_CENTER_ID])
