"""Activities, task status, timeline and timepoints for the ABC UI.

Ported from ``ActivityBasedCuration::Application`` (``RefreshActivities``,
``DrawActivityTaskStatus``, ``ShowActivityTimeline``,
``CountOverlappingEvents``) and the saved queries those methods call.
"""

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass, replace

import asyncpg


class ActivityNotFound(LookupError):
    """No activity row exists for the given id."""


@dataclass(frozen=True)
class Activity:
    activity_id: int
    brief_description: str
    when_created: dt.datetime
    who_created: str
    when_closed: dt.datetime | None
    third_party_analysis_url: str | None


@dataclass(frozen=True)
class TaskStatus:
    subprocess_invocation_id: int
    operation_name: str | None
    start_time: dt.datetime
    last_updated: dt.datetime | None
    status_text: str | None
    expected_remaining_time: dt.timedelta | None
    end_time: dt.datetime | None
    since_update: dt.timedelta | None
    stale_warning: str | None


@dataclass(frozen=True)
class Timepoint:
    activity_timepoint_id: int
    when_created: dt.datetime
    comment: str | None
    creating_user: str | None
    file_count: int
    # when_created is a naive ``timestamp``; this is the same instant as the
    # server's ``timestamptz`` cast, used to compare against script times.
    created_instant: dt.datetime


@dataclass(frozen=True)
class TimelineEvent:
    inbox_content_id: int
    subprocess_invocation_id: int
    operation_name: str | None
    user_name: str
    started: dt.datetime
    ended: dt.datetime | None
    duration: dt.timedelta | None
    command_line: str | None
    email_file_id: int | None
    spreadsheet_file_id: int | None
    timepoint_id: int | None = None
    timepoint_file_count: int | None = None
    overlap_count: int = 0


_ACTIVITY_COLUMNS = (
    "activity_id, brief_description, when_created, who_created,"
    " when_closed, third_party_analysis_url"
)
_OPEN_ACTIVITIES_SQL = (
    f"select {_ACTIVITY_COLUMNS} from activity"
    " where when_closed is null order by activity_id desc"
)
_ALL_ACTIVITIES_SQL = (
    f"select {_ACTIVITY_COLUMNS} from activity order by activity_id desc"
)
_ONE_ACTIVITY_SQL = f"select {_ACTIVITY_COLUMNS} from activity where activity_id = $1"

_TASK_STATUS_SQL = """
    select
      subprocess_invocation_id,
      operation_name,
      start_time,
      last_updated,
      status_text,
      expected_remaining_time,
      end_time,
      now() - last_updated as since_update,
      case
        when end_time is not null then null
        when last_updated is null then 'never updated'
        when last_updated < now() - interval '5 minutes'
          then 'no status update for ' ||
            date_trunc('second', now() - last_updated)
        else null
      end as stale_warning
    from activity_task_status natural join subprocess_invocation
    where activity_id = $1 and dismissed_time is null
    order by start_time
"""

_DISMISS_TASK_STATUS_SQL = """
    update activity_task_status
    set dismissed_time = now(), dismissed_by = $1
    where activity_id = $2
      and subprocess_invocation_id = $3
      and dismissed_time is null
"""

_TIMEPOINTS_SQL = """
    select
      activity_timepoint_id,
      when_created,
      when_created::timestamptz as created_instant,
      comment,
      creating_user,
      (
        select count(file_id)
        from activity_timepoint_file atf
        where atf.activity_timepoint_id = t.activity_timepoint_id
      ) as file_count
    from activity_timepoint t
    where activity_id = $1
    order by when_created desc
"""

_TIMELINE_SQL = """
    select
      user_name,
      user_inbox_content_id,
      operation_name,
      when_script_started,
      when_script_ended,
      when_script_ended - when_script_started as duration,
      file_id,
      subprocess_invocation_id,
      command_line,
      file_id_in_posda as spreadsheet_file_id
    from activity_inbox_content
    natural join user_inbox
    natural join user_inbox_content
    natural join background_subprocess_report
    natural join background_subprocess
    natural join subprocess_invocation
    natural left join spreadsheet_uploaded
    where activity_id = $1
    order by when_script_started desc
"""


def _activity_from_row(row: asyncpg.Record) -> Activity:
    return Activity(**dict(row))


def description_matcher(pattern: str) -> Callable[[str], bool]:
    """Case-insensitive regex like the Perl dropdown filter; literal on a bad one."""
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error:
        needle = pattern.casefold()
        return lambda text: needle in text.casefold()
    return lambda text: compiled.search(text) is not None


async def list_activities(
    conn: asyncpg.Connection,
    *,
    include_closed: bool = False,
    description_filter: str | None = None,
) -> list[Activity]:
    sql = _ALL_ACTIVITIES_SQL if include_closed else _OPEN_ACTIVITIES_SQL
    activities = [_activity_from_row(row) for row in await conn.fetch(sql)]
    if description_filter:
        matches = description_matcher(description_filter)
        activities = [a for a in activities if matches(a.brief_description)]
    return activities


async def get_activity(conn: asyncpg.Connection, activity_id: int) -> Activity:
    row = await conn.fetchrow(_ONE_ACTIVITY_SQL, activity_id)
    if row is None:
        raise ActivityNotFound(f"activity {activity_id} does not exist")
    return _activity_from_row(row)


async def create_activity(conn: asyncpg.Connection, description: str, user: str) -> int:
    description = description.strip()
    if not description:
        raise ValueError("activity description must not be blank")
    return await conn.fetchval(
        "insert into activity (brief_description, when_created, who_created)"
        " values ($1, now(), $2) returning activity_id",
        description,
        user,
    )


async def set_third_party_url(
    conn: asyncpg.Connection, activity_id: int, url: str | None
) -> None:
    """Record (or with ``None`` clear) the activity's third-party analysis URL."""
    status = await conn.execute(
        "update activity set third_party_analysis_url = $1 where activity_id = $2",
        url,
        activity_id,
    )
    if status == "UPDATE 0":
        raise ActivityNotFound(f"activity {activity_id} does not exist")


async def list_task_status(
    conn: asyncpg.Connection, activity_id: int
) -> list[TaskStatus]:
    rows = await conn.fetch(_TASK_STATUS_SQL, activity_id)
    return [TaskStatus(**dict(row)) for row in rows]


async def dismiss_task_status(
    conn: asyncpg.Connection,
    activity_id: int,
    subprocess_invocation_id: int,
    user: str,
) -> bool:
    """Hide a task-status line; False when there was nothing to dismiss."""
    status = await conn.execute(
        _DISMISS_TASK_STATUS_SQL, user, activity_id, subprocess_invocation_id
    )
    return status != "UPDATE 0"


async def list_timepoints(
    conn: asyncpg.Connection, activity_id: int
) -> list[Timepoint]:
    rows = await conn.fetch(_TIMEPOINTS_SQL, activity_id)
    return [Timepoint(**dict(row)) for row in rows]


def _event_from_row(row: asyncpg.Record) -> TimelineEvent:
    return TimelineEvent(
        inbox_content_id=row["user_inbox_content_id"],
        subprocess_invocation_id=row["subprocess_invocation_id"],
        operation_name=row["operation_name"],
        user_name=row["user_name"],
        started=row["when_script_started"],
        ended=row["when_script_ended"],
        duration=row["duration"],
        command_line=row["command_line"],
        email_file_id=row["file_id"],
        spreadsheet_file_id=row["spreadsheet_file_id"],
    )


async def activity_timeline(
    conn: asyncpg.Connection, activity_id: int
) -> list[TimelineEvent]:
    """Report events for an activity, newest first, with their timepoints."""
    rows = await conn.fetch(_TIMELINE_SQL, activity_id)
    events = [_event_from_row(row) for row in rows]
    timepoints = await list_timepoints(conn, activity_id)
    return annotate_timeline(events, timepoints)


def annotate_timeline(
    events: list[TimelineEvent], timepoints: list[Timepoint]
) -> list[TimelineEvent]:
    """Attach the timepoint each event created and count overlapping events.

    Perl walked both newest-first lists in lock-step and only advanced the
    timepoint cursor on a match, so a timepoint created outside any finished
    event hid every older match. Here each event claims the first unclaimed
    timepoint created while it ran.
    """
    unclaimed = list(timepoints)
    annotated: list[TimelineEvent] = []
    for index, event in enumerate(events):
        timepoint = _claim_timepoint(event, unclaimed)
        annotated.append(
            replace(
                event,
                timepoint_id=timepoint.activity_timepoint_id if timepoint else None,
                timepoint_file_count=timepoint.file_count if timepoint else None,
                overlap_count=count_overlaps(event, events[index + 1 :]),
            )
        )
    return annotated


def _claim_timepoint(
    event: TimelineEvent, unclaimed: list[Timepoint]
) -> Timepoint | None:
    if event.ended is None:
        return None
    for timepoint in unclaimed:
        if event.started <= timepoint.created_instant <= event.ended:
            unclaimed.remove(timepoint)
            return timepoint
    return None


def count_overlaps(event: TimelineEvent, later: list[TimelineEvent]) -> int:
    """Port of ``CountOverlappingEvents``: events touching this one's window.

    Only the events listed after this one are counted (Perl consumed the list
    as it rendered), and an event that has not ended overlaps nothing.
    """
    if event.ended is None:
        return 0
    count = 0
    for other in later:
        if _within(other.started, event) or _within(other.ended, event):
            count += 1
    return count


def _within(instant: dt.datetime | None, event: TimelineEvent) -> bool:
    if instant is None or event.ended is None:
        return False
    return event.started <= instant <= event.ended
