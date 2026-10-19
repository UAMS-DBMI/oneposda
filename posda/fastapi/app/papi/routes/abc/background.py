"""The background job list (Posda::BackgroundList)."""

from datetime import datetime, timedelta
from typing import Literal

import asyncpg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...services import background_jobs
from .deps import Conn

router = APIRouter()


class BackgroundJobOut(BaseModel):
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


class BackgroundJobsOut(BaseModel):
    jobs: list[BackgroundJobOut]
    total: int
    limit: int


@router.get("", response_model=BackgroundJobsOut)
async def list_jobs(
    conn: Conn,
    mode: Literal["all", "running", "errored", "finished"] = Query(default="all"),
    in_last: str | None = Query(default="12 hours"),
) -> BackgroundJobsOut:
    try:
        found = await background_jobs.list_jobs(conn, mode=mode, in_last=in_last)
    except asyncpg.DataError as exc:
        raise HTTPException(status_code=400, detail=f"bad interval: {exc}")
    return BackgroundJobsOut(
        jobs=[BackgroundJobOut(**job.__dict__) for job in found.jobs],
        total=found.total,
        limit=background_jobs.ROW_LIMIT,
    )
