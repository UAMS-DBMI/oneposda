"""The user inbox: report emails from background operations (Posda::Inbox)."""

from dataclasses import dataclass
from datetime import datetime

import asyncpg

UNREAD_STATUSES = ("entered", "new")


class InboxItemNotFound(LookupError):
    pass


class NoSuchInboxUser(LookupError):
    pass


@dataclass(frozen=True)
class InboxItem:
    user_inbox_content_id: int
    background_subprocess_report_id: int | None
    current_status: str | None
    date_entered: datetime | None
    date_dismissed: datetime | None
    operation_name: str | None
    report_name: str | None


@dataclass(frozen=True)
class InboxItemDetail(InboxItem):
    file_id: int | None
    subprocess_invocation_id: int | None
    command_line: str | None
    invoking_user: str | None
    filed_activity_id: int | None


@dataclass(frozen=True)
class InboxOperation:
    operation_type: str | None
    when_occurred: datetime | None
    invoking_user: str | None
    how_invoked: str | None


_ITEM_SQL = """
    select c.user_inbox_content_id, c.background_subprocess_report_id,
           c.current_status, c.date_entered, c.date_dismissed,
           s.operation_name, r.name as report_name
    from user_inbox_content c
    join user_inbox u using (user_inbox_id)
    left join background_subprocess_report r using (background_subprocess_report_id)
    left join background_subprocess b using (background_subprocess_id)
    left join subprocess_invocation s using (subprocess_invocation_id)
    where u.user_name = $1
"""


def _item(row: asyncpg.Record) -> InboxItem:
    return InboxItem(
        user_inbox_content_id=row["user_inbox_content_id"],
        background_subprocess_report_id=row["background_subprocess_report_id"],
        current_status=row["current_status"],
        date_entered=row["date_entered"],
        date_dismissed=row["date_dismissed"],
        operation_name=row["operation_name"],
        report_name=row["report_name"],
    )


async def unread_count(conn: asyncpg.Connection, user: str) -> int:
    return int(
        await conn.fetchval(
            """
            select count(*) from user_inbox_content natural join user_inbox
            where current_status = any($2) and date_dismissed is null and user_name = $1
            """,
            user,
            list(UNREAD_STATUSES),
        )
    )


async def list_items(
    conn: asyncpg.Connection, user: str, *, include_dismissed: bool = False
) -> list[InboxItem]:
    rows = await conn.fetch(
        _ITEM_SQL
        + " and ($2 or c.date_dismissed is null) order by c.user_inbox_content_id desc",
        user,
        include_dismissed,
    )
    return [_item(r) for r in rows]


async def get_item(
    conn: asyncpg.Connection, user: str, item_id: int
) -> InboxItemDetail:
    row = await conn.fetchrow(
        """
        select c.user_inbox_content_id, c.background_subprocess_report_id,
               c.current_status, c.date_entered, c.date_dismissed,
               s.operation_name, r.name as report_name, r.file_id,
               s.subprocess_invocation_id, s.command_line, s.invoking_user,
               (select min(activity_id) from activity_inbox_content a
                 where a.user_inbox_content_id = c.user_inbox_content_id) as filed_activity_id
        from user_inbox_content c
        join user_inbox u using (user_inbox_id)
        left join background_subprocess_report r using (background_subprocess_report_id)
        left join background_subprocess b using (background_subprocess_id)
        left join subprocess_invocation s using (subprocess_invocation_id)
        where u.user_name = $1 and c.user_inbox_content_id = $2
        """,
        user,
        item_id,
    )
    if row is None:
        raise InboxItemNotFound(item_id)
    return InboxItemDetail(
        **_item(row).__dict__,
        file_id=row["file_id"],
        subprocess_invocation_id=row["subprocess_invocation_id"],
        command_line=row["command_line"],
        invoking_user=row["invoking_user"],
        filed_activity_id=row["filed_activity_id"],
    )


async def recent_operations(
    conn: asyncpg.Connection, item_id: int
) -> list[InboxOperation]:
    rows = await conn.fetch(
        """
        select operation_type, when_occurred, invoking_user, how_invoked
        from user_inbox_content_operation
        where user_inbox_content_id = $1
        order by when_occurred desc, ctid desc limit 15
        """,
        item_id,
    )
    return [InboxOperation(**dict(r)) for r in rows]


async def _change_status(
    conn: asyncpg.Connection, user: str, item_id: int, status: str, operation: str
) -> None:
    await conn.execute(
        "update user_inbox_content set current_status = $2 where user_inbox_content_id = $1",
        item_id,
        status,
    )
    await conn.execute(
        """
        insert into user_inbox_content_operation
          (user_inbox_content_id, operation_type, when_occurred, how_invoked, invoking_user)
        values ($1, $2, now(), 'ABC API', $3)
        """,
        item_id,
        operation,
        user,
    )


async def mark_read(conn: asyncpg.Connection, user: str, item_id: int) -> None:
    await _change_status(conn, user, item_id, "read", "message read")


async def dismiss(conn: asyncpg.Connection, user: str, item_id: int) -> None:
    await _change_status(conn, user, item_id, "dismissed", "message dismissed")
    await conn.execute(
        "update user_inbox_content set date_dismissed = now() where user_inbox_content_id = $1",
        item_id,
    )


async def file_to_activity(
    conn: asyncpg.Connection, user: str, item_id: int, activity_id: int
) -> None:
    """Attach the report to an activity's timeline and dismiss it."""
    await conn.execute(
        "insert into activity_inbox_content (activity_id, user_inbox_content_id) values ($1, $2)",
        activity_id,
        item_id,
    )
    await dismiss(conn, user, item_id)


async def usernames(conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch("select user_name from user_inbox order by user_name")
    return [r["user_name"] for r in rows]


async def forward(
    conn: asyncpg.Connection, user: str, item: InboxItemDetail, to_user: str
) -> int:
    """Copy the item into another user's inbox; returns the new item id."""
    inbox_id = await conn.fetchval(
        "select user_inbox_id from user_inbox where user_name = $1", to_user
    )
    if inbox_id is None:
        raise NoSuchInboxUser(to_user)
    note = await conn.fetchval(
        "select statuts_note from user_inbox_content where user_inbox_content_id = $1",
        item.user_inbox_content_id,
    )
    new_id = await conn.fetchval(
        """
        insert into user_inbox_content
          (user_inbox_id, background_subprocess_report_id, current_status,
           statuts_note, date_entered, date_dismissed)
        values ($1, $2, 'entered', $3, now(), null)
        returning user_inbox_content_id
        """,
        inbox_id,
        item.background_subprocess_report_id,
        note,
    )
    await conn.execute(
        """
        insert into user_inbox_content_operation
          (user_inbox_content_id, operation_type, when_occurred, how_invoked, invoking_user)
        values ($1, 'entered', now(), 'manually forwarded', $2)
        """,
        new_id,
        user,
    )
    return int(new_id)
