"""Foreground query runs: start, watch, page, filter, control, download."""

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...services.queries import runner
from ...services.queries.csv_export import CsvHeader, format_when, iter_csv
from ...services.queries.rowstore import RowStoreReader, RowStoreError
from ...services.settings import get_settings
from .deps import Conn, CurrentUser, Pools

router = APIRouter()

DEFAULT_PAGE = 30
MAX_PAGE = 1000


class StartRun(BaseModel):
    query_name: str
    args: dict[str, str | None] = {}


class StartedRun(BaseModel):
    query_run_id: int


class RunOut(BaseModel):
    query_run_id: int
    query_name: str
    args: dict[str, str | None]
    caption: str
    state: str
    requested_action: str | None
    is_select: bool | None
    row_count: int
    rows_affected: int | None
    error_text: str | None
    filter: dict[str, str] | None
    view_filtered: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    dismissed_at: datetime | None
    owner: str | None


class RunDetailOut(RunOut):
    columns: list[str]
    filtered_count: int | None


class RowsOut(BaseModel):
    first: int
    rows: list[list[Any]]
    total: int
    filtered: bool
    partial: bool


class FilterIn(BaseModel):
    filter: dict[str, str] | None
    view_filtered: bool = True


def _run_out(run: runner.Run) -> RunOut:
    return RunOut(
        query_run_id=run.query_run_id,
        query_name=run.query_name,
        args=run.args,
        caption=run.caption,
        state=run.state,
        requested_action=run.requested_action,
        is_select=run.is_select,
        row_count=run.row_count,
        rows_affected=run.rows_affected,
        error_text=run.error_text,
        filter=run.filter,
        view_filtered=run.view_filtered,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        dismissed_at=run.dismissed_at,
        owner=run.owner,
    )


async def _load(conn: Conn, run_id: int, user: CurrentUser) -> runner.Run:
    try:
        return await runner.load_users_run(conn, run_id, user.username)
    except runner.RunNotFound:
        raise HTTPException(status_code=404, detail=f"query run {run_id} not found")


@router.post("", response_model=StartedRun, status_code=201)
async def start_run(
    body: StartRun, conn: Conn, pools: Pools, user: CurrentUser
) -> StartedRun:
    try:
        run_id = await runner.start_run(
            conn,
            pools,
            get_settings(),
            query_name=body.query_name,
            args=body.args,
            user=user.username,
        )
    except runner.RunLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except runner.RunError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return StartedRun(query_run_id=run_id)


@router.get("", response_model=list[RunOut])
async def list_runs(
    conn: Conn, user: CurrentUser, include_dismissed: bool = Query(default=False)
) -> list[RunOut]:
    runs = await runner.list_runs(
        conn, user.username, include_dismissed=include_dismissed
    )
    return [_run_out(r) for r in runs]


@router.get("/{run_id}", response_model=RunDetailOut)
async def run_detail(run_id: int, conn: Conn, user: CurrentUser) -> RunDetailOut:
    run = await _load(conn, run_id, user)
    try:
        columns = runner.read_columns(run.spool_dir)
    except runner.RunNotFound:
        raise HTTPException(
            status_code=410, detail="the results of this run have been removed"
        )
    filtered_count = None
    if run.filter:
        try:
            view = await runner.filtered_view(run)
        except RowStoreError:
            view = None
        filtered_count = view.count if view else None
    return RunDetailOut(
        **_run_out(run).model_dump(), columns=columns, filtered_count=filtered_count
    )


@router.get("/{run_id}/rows", response_model=RowsOut)
async def run_rows(
    run_id: int,
    conn: Conn,
    user: CurrentUser,
    first: int = Query(default=0, ge=0),
    n: int = Query(default=DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    filtered: bool = Query(default=False),
) -> RowsOut:
    run = await _load(conn, run_id, user)
    use_filter = filtered and bool(run.filter)
    try:
        page, total = await runner.page(run, first, n, filtered=use_filter)
    except RowStoreError, runner.RunNotFound:
        if run.row_count == 0:
            return RowsOut(
                first=first, rows=[], total=0, filtered=use_filter, partial=False
            )
        raise HTTPException(
            status_code=410, detail="the results of this run have been removed"
        )
    return RowsOut(
        first=first,
        rows=page.rows,
        total=total,
        filtered=use_filter,
        partial=page.partial,
    )


@router.put("/{run_id}/filter", response_model=RunDetailOut)
async def set_filter(
    run_id: int, body: FilterIn, conn: Conn, user: CurrentUser
) -> RunDetailOut:
    run = await _load(conn, run_id, user)
    try:
        await runner.set_filter(conn, run, body.filter, body.view_filtered)
    except runner.RunError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except runner.RunNotFound:
        raise HTTPException(
            status_code=410, detail="the results of this run have been removed"
        )
    return await run_detail(run_id, conn, user)


async def _control(conn: Conn, run_id: int, user: CurrentUser, action) -> RunOut:
    run = await _load(conn, run_id, user)
    try:
        await action(run)
    except runner.BadRunState as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _run_out(await runner.load_run(conn, run_id))


@router.post("/{run_id}/pause", response_model=RunOut)
async def pause_run(run_id: int, conn: Conn, user: CurrentUser) -> RunOut:
    return await _control(
        conn, run_id, user, lambda run: runner.request_pause(conn, run)
    )


@router.post("/{run_id}/resume", response_model=RunOut)
async def resume_run(run_id: int, conn: Conn, user: CurrentUser) -> RunOut:
    return await _control(
        conn, run_id, user, lambda run: runner.request_resume(conn, run)
    )


@router.post("/{run_id}/abort", response_model=RunOut)
async def abort_run(run_id: int, conn: Conn, pools: Pools, user: CurrentUser) -> RunOut:
    return await _control(
        conn, run_id, user, lambda run: runner.request_abort(conn, pools, run)
    )


@router.post("/{run_id}/dismiss", response_model=RunOut)
async def dismiss_run(run_id: int, conn: Conn, user: CurrentUser) -> RunOut:
    return await _control(conn, run_id, user, lambda run: runner.dismiss(conn, run))


@router.post("/{run_id}/rerun", response_model=StartedRun, status_code=201)
async def rerun(run_id: int, conn: Conn, pools: Pools, user: CurrentUser) -> StartedRun:
    run = await _load(conn, run_id, user)
    return await start_run(
        StartRun(query_name=run.query_name, args=run.args), conn, pools, user
    )


@router.get("/{run_id}/csv")
async def download_csv(
    run_id: int, conn: Conn, user: CurrentUser, filtered: bool = Query(default=False)
) -> StreamingResponse:
    run = await _load(conn, run_id, user)
    try:
        columns = runner.read_columns(run.spool_dir)
    except runner.RunNotFound:
        raise HTTPException(
            status_code=410, detail="the results of this run have been removed"
        )
    view = await runner.filtered_view(run) if run.filter else None
    use_filter = filtered and view is not None
    header = CsvHeader(
        caption=run.caption,
        when=format_when(run.started_at or run.created_at),
        who=run.invoking_user,
        columns=columns,
        filter_spec=run.filter or None,
        unfiltered_rows=run.row_count,
        filtered_rows=view.count if view else None,
    )
    if use_filter and view is not None:
        reader = RowStoreReader(run.spool_dir, view.name)
        available = view.count
    else:
        reader = RowStoreReader(run.spool_dir)
        available = run.row_count

    async def chunks():
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=4)
        loop = asyncio.get_running_loop()

        def produce() -> None:
            try:
                for chunk in iter_csv(
                    header, reader.iterate(available=available), filtered=use_filter
                ):
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

        producer = asyncio.create_task(asyncio.to_thread(produce))
        try:
            while (chunk := await queue.get()) is not None:
                yield chunk
        finally:
            await producer

    filename = f"{run.query_name}.csv"
    return StreamingResponse(
        chunks(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
