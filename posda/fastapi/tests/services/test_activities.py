import datetime as dt

import asyncpg
import pytest

from papi.services.activities import (
    ActivityNotFound,
    Timepoint,
    TimelineEvent,
    activity_timeline,
    annotate_timeline,
    count_overlaps,
    create_activity,
    description_matcher,
    dismiss_task_status,
    get_activity,
    list_activities,
    list_task_status,
    list_timepoints,
    set_third_party_url,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def event(
    sub_id: int, start_min: int, end_min: int | None, **extra: object
) -> TimelineEvent:
    return TimelineEvent(
        inbox_content_id=sub_id * 10,
        subprocess_invocation_id=sub_id,
        operation_name=f"Op{sub_id}",
        user_name="u",
        started=T0 + dt.timedelta(minutes=start_min),
        ended=None if end_min is None else T0 + dt.timedelta(minutes=end_min),
        duration=None,
        command_line="cmd",
        email_file_id=None,
        spreadsheet_file_id=None,
        **extra,
    )


def timepoint(tp_id: int, created_min: int, files: int = 0) -> Timepoint:
    instant = T0 + dt.timedelta(minutes=created_min)
    return Timepoint(
        activity_timepoint_id=tp_id,
        when_created=instant.replace(tzinfo=None),
        comment=None,
        creating_user="u",
        file_count=files,
        created_instant=instant,
    )


# --- pure functions -------------------------------------------------------


def test_each_event_claims_the_timepoint_created_during_it() -> None:
    events = [event(3, 20, 30), event(2, 10, 15), event(1, 0, 5)]
    timepoints = [timepoint(30, 25, files=7), timepoint(10, 2, files=1)]

    annotated = annotate_timeline(events, timepoints)

    assert [(e.timepoint_id, e.timepoint_file_count) for e in annotated] == [
        (30, 7),
        (None, None),
        (10, 1),
    ]


def test_a_stray_timepoint_does_not_block_older_matches() -> None:
    # Perl's lock-step walk would have stopped at the stray timepoint (minute 50).
    events = [event(2, 10, 15), event(1, 0, 5)]
    timepoints = [timepoint(99, 50), timepoint(10, 12)]

    annotated = annotate_timeline(events, timepoints)

    assert [e.timepoint_id for e in annotated] == [10, None]


def test_unfinished_event_claims_nothing() -> None:
    annotated = annotate_timeline([event(1, 0, None)], [timepoint(1, 1)])
    assert annotated[0].timepoint_id is None


def test_overlaps_count_only_later_events() -> None:
    newest = event(3, 20, 40)
    middle = event(2, 30, 35)  # entirely inside newest
    oldest = event(1, 0, 25)  # ends inside newest
    unrelated = event(0, 50, 60)

    assert count_overlaps(newest, [middle, oldest, unrelated]) == 2
    assert count_overlaps(middle, [oldest]) == 0
    assert count_overlaps(event(9, 0, None), [middle]) == 0


def test_description_matcher_is_regex_with_literal_fallback() -> None:
    assert description_matcher("lung.*ct")("LUNG screening CT")
    assert not description_matcher("^ct")("Lung CT")
    assert description_matcher("a(b")("has a(b in it")


# --- database -------------------------------------------------------------


async def test_create_list_and_update(conn: asyncpg.Connection) -> None:
    activity_id = await create_activity(conn, "  ABC test activity  ", "tester")

    created = await get_activity(conn, activity_id)
    assert created.brief_description == "ABC test activity"
    assert created.who_created == "tester"
    assert created.third_party_analysis_url is None

    listed = await list_activities(conn, description_filter="abc test")
    assert [a.activity_id for a in listed] == [activity_id]

    await set_third_party_url(conn, activity_id, "https://example.org/x")
    assert (await get_activity(conn, activity_id)).third_party_analysis_url == (
        "https://example.org/x"
    )
    await set_third_party_url(conn, activity_id, None)
    assert (await get_activity(conn, activity_id)).third_party_analysis_url is None


async def test_closed_activities_hidden_by_default(conn: asyncpg.Connection) -> None:
    activity_id = await create_activity(conn, "ABC closed test", "tester")
    await conn.execute(
        "update activity set when_closed = now() where activity_id = $1", activity_id
    )

    assert activity_id not in {a.activity_id for a in await list_activities(conn)}
    assert activity_id in {
        a.activity_id for a in await list_activities(conn, include_closed=True)
    }


async def test_blank_description_rejected(conn: asyncpg.Connection) -> None:
    with pytest.raises(ValueError):
        await create_activity(conn, "   ", "tester")


async def test_missing_activity_raises(conn: asyncpg.Connection) -> None:
    with pytest.raises(ActivityNotFound):
        await get_activity(conn, -1)
    with pytest.raises(ActivityNotFound):
        await set_third_party_url(conn, -1, "x")


async def test_task_status_and_dismiss(conn: asyncpg.Connection) -> None:
    activity_id = await create_activity(conn, "ABC status test", "tester")
    sub_id = await conn.fetchval(
        "insert into subprocess_invocation (operation_name, when_invoked)"
        " values ('TestOp', now()) returning subprocess_invocation_id"
    )
    await conn.execute(
        "insert into activity_task_status"
        " (activity_id, subprocess_invocation_id, status_text, start_time,"
        "  last_updated)"
        " values ($1, $2, 'working', now(), now() - interval '10 minutes')",
        activity_id,
        sub_id,
    )

    [status] = await list_task_status(conn, activity_id)
    assert status.operation_name == "TestOp"
    assert status.status_text == "working"
    assert status.stale_warning is not None
    assert status.stale_warning.startswith("no status update for")

    assert await dismiss_task_status(conn, activity_id, sub_id, "tester") is True
    assert await list_task_status(conn, activity_id) == []
    assert await dismiss_task_status(conn, activity_id, sub_id, "tester") is False


async def test_timeline_matches_timepoint_created_during_run(
    conn: asyncpg.Connection,
) -> None:
    activity_id = await create_activity(conn, "ABC timeline test", "tester")
    sub_id = await conn.fetchval(
        "insert into subprocess_invocation (operation_name, command_line,"
        " when_invoked) values ('TestOp', 'TestOp.pl', now())"
        " returning subprocess_invocation_id"
    )
    bkg_id = await conn.fetchval(
        "insert into background_subprocess (subprocess_invocation_id,"
        " when_script_started, when_script_ended)"
        " values ($1, now() - interval '20 minutes', now() - interval '10 minutes')"
        " returning background_subprocess_id",
        sub_id,
    )
    report_id = await conn.fetchval(
        "insert into background_subprocess_report"
        " (background_subprocess_id, file_id, name)"
        " values ($1, 1, 'Email') returning background_subprocess_report_id",
        bkg_id,
    )
    inbox_id = await conn.fetchval(
        "insert into user_inbox (user_name) values ('abc-timeline-tester')"
        " returning user_inbox_id"
    )
    content_id = await conn.fetchval(
        "insert into user_inbox_content"
        " (user_inbox_id, background_subprocess_report_id, current_status,"
        "  date_entered)"
        " values ($1, $2, 'new', now()) returning user_inbox_content_id",
        inbox_id,
        report_id,
    )
    await conn.execute(
        "insert into activity_inbox_content (activity_id, user_inbox_content_id)"
        " values ($1, $2)",
        activity_id,
        content_id,
    )
    tp_id = await conn.fetchval(
        "insert into activity_timepoint (activity_id, when_created, creating_user)"
        " values ($1, now() - interval '15 minutes', 'tester')"
        " returning activity_timepoint_id",
        activity_id,
    )

    [tp] = await list_timepoints(conn, activity_id)
    assert tp.activity_timepoint_id == tp_id and tp.file_count == 0

    [entry] = await activity_timeline(conn, activity_id)
    assert entry.subprocess_invocation_id == sub_id
    assert entry.timepoint_id == tp_id
    assert entry.email_file_id == 1
    assert entry.duration == dt.timedelta(minutes=10)
