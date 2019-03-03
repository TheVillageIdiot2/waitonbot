import dataclasses
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Tuple, List, Optional, Any

import google_api
from plugins import scroll_util

SHEET_ID = "1f9p4H7TWPm8rAM4v_qr2Vc6lBiFNEmR-quTY9UtxEBI"

# Note: These ranges use named range feature of google sheets.
# To edit range of jobs, edit the named range in Data -> Named Ranges
job_range = "AllJobs"  # Note that the first row is headers
point_range = "PointRange"

# How tolerant of spelling errors in names to be
SHEET_LOOKUP_THRESHOLD = 80.0

JOB_VAL = 1
LATE_VAL = 0.5
MISS_VAL = -1
SIGNOFF_VAL = 0.1
TOWEL_VAL = 0.1

# What to put for a non-signed-off job
SIGNOFF_PLACEHOLDER = "E-SIGNOFF"
NOT_ASSIGNED = "N/A"


@dataclass
class Job(object):
    """
    Represents a job in a more internally meaningful way.
    """
    name: str
    house: str
    day_of_week: str
    # Extra stuff, interpreted
    day: Optional[date]

    def pretty_fmt(self) -> str:
        return "{} - {} at {}".format(self.name, self.day_of_week, self.house)


@dataclass
class JobAssignment(object):
    """
    Tracks a job's assignment and completion
    """
    job: Job
    assignee: Optional[scroll_util.Brother]
    signer: Optional[scroll_util.Brother]
    late: bool
    bonus: bool

    def to_raw(self) -> Tuple[str, str, str, str, str, str, str]:
        # Converts this back into a spreadsheet row
        signer_name = self.signer.name if self.signer is not None else SIGNOFF_PLACEHOLDER
        late = "y" if self.late else "n"
        bonus = "y" if self.bonus else "n"
        assignee = self.assignee.name if self.assignee else NOT_ASSIGNED
        return self.job.name, self.job.house, self.job.day_of_week, assignee, signer_name, late, bonus


@dataclass
class PointStatus(object):
    """
    Tracks a brothers points
    """
    brother: scroll_util.Brother
    job_points: float = 0
    signoff_points: float = 0
    towel_points: float = 0
    work_party_points: float = 0
    bonus_points: float = 0

    def to_raw(self) -> Tuple[str, float, float, float, float, float]:
        # Convert to a row. Also, do some rounding while we're at it
        def fmt(x: float):
            return round(x, 2)

        return (self.brother.name,
                fmt(self.job_points),
                fmt(self.signoff_points),
                fmt(self.towel_points),
                fmt(self.work_party_points),
                fmt(self.bonus_points),
                )

    @property
    def towel_contribution_count(self) -> int:
        return round(self.towel_points / TOWEL_VAL)

    @towel_contribution_count.setter
    def towel_contribution_count(self, val: int) -> None:
        self.towel_points = val * TOWEL_VAL


def strip_all(l: List[str]) -> List[str]:
    return [x.strip() for x in l]


async def import_assignments() -> List[Optional[JobAssignment]]:
    """
    Imports Jobs and JobAssignments from the sheet. 1:1 row correspondence.
    """
    # Get the raw data
    job_rows = google_api.get_sheet_range(SHEET_ID, job_range)

    # None-out invalid rows (length not at least 4, which includes the 4 most important features)
    def fixer(row):
        if len(row) == 4:
            return strip_all(row + [SIGNOFF_PLACEHOLDER, "n", "n"])
        elif len(row) == 5:
            return strip_all(row + ["n", "n"])
        elif len(row) == 6:
            return strip_all(row + ["n"])
        elif len(row) == 7:
            return strip_all(row)
        else:
            return None

    # Apply the fix
    job_rows = [fixer(row) for row in job_rows]

    # Now, create jobs
    assignments = []
    for row in job_rows:
        if row is None:
            assignments.append(None)
        else:
            # Breakout list
            job_name, location, day, assignee, signer, late, bonus = row

            # Figure out when the day actually is, in terms of the date class
            day_rank = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6
            }.get(day.lower(), None)

            if day_rank is not None:
                # Figure out current date day of week, and extrapolate the jobs day of week from there
                today = date.today()
                today_rank = today.weekday()

                days_till = day_rank - today_rank
                if days_till <= 0:
                    days_till += 7

                # Now we know what day it is!
                job_day = today + timedelta(days=days_till)
            else:
                # Can't win 'em all
                job_day = None

            # Create the job
            job = Job(name=job_name, house=location, day_of_week=day, day=job_day)

            # Now make an assignment for the job
            # Find the brother it is assigned to
            if assignee is not None and assignee != "" and assignee != NOT_ASSIGNED:
                try:
                    assignee = await scroll_util.find_by_name(assignee, SHEET_LOOKUP_THRESHOLD)
                except scroll_util.BrotherNotFound:
                    # If we can't get one close enough, make a dummy
                    assignee = scroll_util.Brother(assignee, scroll_util.MISSINGBRO_SCROLL)
            else:
                assignee = None

            # Find the brother who is currently listed as having signed it off
            try:
                if signer == SIGNOFF_PLACEHOLDER:
                    signer = None
                else:
                    signer = await scroll_util.find_by_name(signer)
            except scroll_util.BrotherNotFound:
                # If we can't figure out the name
                signer = None

            # Make late a bool
            late = late == "y"

            # Ditto for bonus
            bonus = bonus == "y"

            # Create the assignment
            assignment = JobAssignment(job=job, assignee=assignee, signer=signer, late=late, bonus=bonus)

            # Append to job/assignment lists
            assignments.append(assignment)

    # Git 'em gone
    return assignments


async def export_assignments(assigns: List[Optional[JobAssignment]]) -> None:
    # Smash to rows
    rows = []
    for v in assigns:
        if v is None:
            rows.append([""] * 7)
        else:
            rows.append(list(v.to_raw()))

    # Send to google
    google_api.set_sheet_range(SHEET_ID, job_range, rows)


async def import_points() -> (List[str], List[PointStatus]):
    # Figure out how many things there are in a point status
    field_count = len(dataclasses.fields(PointStatus))

    # Get the raw data
    point_rows = google_api.get_sheet_range(SHEET_ID, point_range)

    # Get the headers
    headers = point_rows[0]
    point_rows = point_rows[1:]

    # Tidy rows up
    async def converter(row: List[Any]) -> Optional[PointStatus]:
        # If its too long, or empty already, ignore
        if len(row) == 0 or len(row) > field_count:
            return None

        # Ensure its the proper length
        while len(row) < field_count:
            row: List[Any] = row + [0]

        # Ensure all past the first column are float. If can't convert, make 0
        for i in range(1, len(row)):
            try:
                x = float(row[i])
            except ValueError:
                x = 0
            row[i] = x

        # Get the brother for the last item
        try:
            brother = await scroll_util.find_by_name(row[0])
        except scroll_util.BrotherNotFound:
            brother = scroll_util.Brother(row[0], scroll_util.MISSINGBRO_SCROLL)

        # Ok! Now, we just map it directly to a PointStatus
        status = PointStatus(brother, *(row[1:]))
        return status

    # Perform conversion and return
    point_statuses = [await converter(row) for row in point_rows]
    return headers, point_statuses


def export_points(headers: List[str], points: List[PointStatus]) -> None:
    # Smash to rows
    rows = [list(point_status.to_raw()) for point_status in points]
    rows = [headers] + rows

    # Send to google
    google_api.set_sheet_range(SHEET_ID, point_range, rows)


def apply_house_points(points: List[PointStatus], assigns: List[Optional[JobAssignment]]):
    """
    Modifies the points list to reflect job assignment scores.
    Destroys existing values in the column.
    Should be called each time we re-export, for validations sake.
    """
    # First, eliminate all house points and signoff points
    for p in points:
        p.job_points = 0
        p.signoff_points = 0

    # Then, apply each assign
    for a in assigns:
        # Ignore null assigns
        if a is None:
            continue

        # What modifier should this have?
        if a.signer is None:
            job_score = MISS_VAL
        else:
            if a.late:
                job_score = LATE_VAL
            else:
                job_score = JOB_VAL

        # Find the corr bro in points
        for p in points:
            # If we find assignee, add the score, but don't stop looking since we also need to find signer
            if p.brother == a.assignee:
                p.job_points += job_score

            # If we find the signer, add a signoff reward
            if p.brother == a.signer:
                p.signoff_points += SIGNOFF_VAL
