"""The "Show Background" list: every subprocess_invocation with its work row."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import asyncpg

Mode = Literal["all", "running", "errored", "finished"]
ROW_LIMIT = 100


@dataclass(frozen=True)
class BackgroundJob:
    subprocess_invocation_id: int
    work_id: int | None
    background_subprocess_id: int | None
    activity_id: int | None
    status: str | None
    input_file_id: int | None
    stdout_file_id: int | None
    stderr_file_id: int | None
    invoking_user: str | None
    since_invocation: timedelta | None
    command_line: str | None
    when_invoked: datetime | None
    user_to_notify: str | None
    node_hostname: str | None
    background_queue_name: str | None


@dataclass(frozen=True)
class BackgroundJobs:
    jobs: list[BackgroundJob]
    total: int


_SQL = """
    select subprocess_invocation_id, work_id, background_subprocess_id,
           activity_id, status, input_file_id, stdout_file_id, stderr_file_id,
           invoking_user, now() - when_invoked as since_invocation, command_line,
           when_invoked, user_to_notify, node_hostname, background_queue_name,
           count(*) over () as total
    from subprocess_invocation
    left join work using (subprocess_invocation_id)
    left join background_subprocess using (subprocess_invocation_id)
    left join activity_task_status using (subprocess_invocation_id)
    where ($1::text is null or status = $1)
      and ($2::text is null
           or (when_invoked > now() - $2::text::interval and when_invoked < now()))
    order by subprocess_invocation_id desc
    limit $3
"""


async def list_jobs(
    conn: asyncpg.Connection, *, mode: Mode = "all", in_last: str | None = None
) -> BackgroundJobs:
    status = None if mode == "all" else mode
    interval = in_last.strip() if in_last and in_last.strip() else None
    rows = await conn.fetch(_SQL, status, interval, ROW_LIMIT)
    jobs = [
        BackgroundJob(**{k: v for k, v in dict(r).items() if k != "total"})
        for r in rows
    ]
    total = int(rows[0]["total"]) if rows else 0
    return BackgroundJobs(jobs=jobs, total=total)
