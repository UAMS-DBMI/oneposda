"""Foreground query runs.

A run is a ``query_run`` row plus a spool directory on the shared cache
volume. ``start_run`` records the run and schedules ``execute_run`` as a task
in the API process that received the request; every other process serves
pages, filters, downloads and control requests from the row and the spool,
so the UI works the same whichever replica answers.

Control flows through the row: a pause, resume or abort request sets
``requested_action`` and the executing task sees it at its next heartbeat
(every batch of rows). Abort additionally cancels the backend query so a
long-running statement that has not yet produced a batch stops too. A task
that dies without updating its heartbeat is marked ``lost`` by the janitor.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import socket
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg

from .. import bindings
from ..db_pools import PoolRegistry
from ..settings import Settings
from . import catalog, log
from .filters import (
    Filter,
    FilteredView,
    build_view,
    existing_view,
    filter_key,
    normalise,
)
from .params import check_arg_count, prepare_text_bound, tokenize
from .rowstore import Page, RowStoreReader, RowStoreWriter

logger = logging.getLogger(__name__)

BATCH_ROWS = 1000
# A slow query is checked for pause/abort requests at least this often even
# when a batch is not full, so control latency stays near this bound.
CONTROL_INTERVAL_SECONDS = 1.0
CURSOR_PREFETCH = 250
PAUSE_POLL_SECONDS = 1.0
TERMINAL_STATES = frozenset({"done", "ended", "aborted", "error", "lost"})
ACTIVE_STATES = frozenset({"queued", "running", "paused"})

_tasks: set[asyncio.Task[None]] = set()


class RunError(RuntimeError):
    pass


class RunNotFound(LookupError):
    pass


class RunLimitExceeded(RunError):
    pass


class BadRunState(RunError):
    pass


class _Aborted(Exception):
    def __init__(self, *, was_paused: bool) -> None:
        self.was_paused = was_paused


@dataclass(frozen=True)
class Run:
    query_run_id: int
    query_name: str
    args: dict[str, str | None]
    caption: str
    invoking_user: str
    query_invoked_by_dbif_id: int | None
    state: str
    requested_action: str | None
    owner: str | None
    backend_db: str | None
    backend_pid: int | None
    is_select: bool | None
    row_count: int
    rows_affected: int | None
    error_text: str | None
    spool_dir: Path
    filter: Filter | None
    view_filtered: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_heartbeat: datetime | None
    dismissed_at: datetime | None

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_STATES


_RUN_COLUMNS = """
    query_run_id, query_name, args, caption, invoking_user,
    query_invoked_by_dbif_id, state, requested_action, owner, backend_db,
    backend_pid, is_select, row_count, rows_affected, error_text, spool_dir,
    filter, view_filtered, created_at, started_at, finished_at, last_heartbeat,
    dismissed_at
"""


def _run_from(row: asyncpg.Record) -> Run:
    data = dict(row)
    data["args"] = (
        json.loads(data["args"]) if isinstance(data["args"], str) else data["args"]
    )
    raw_filter = data["filter"]
    data["filter"] = (
        json.loads(raw_filter) if isinstance(raw_filter, str) else raw_filter
    )
    data["spool_dir"] = Path(data["spool_dir"])
    return Run(**data)


async def load_run(conn: asyncpg.Connection, run_id: int) -> Run:
    row = await conn.fetchrow(
        f"select {_RUN_COLUMNS} from query_run where query_run_id = $1", run_id
    )
    if row is None:
        raise RunNotFound(run_id)
    return _run_from(row)


async def load_users_run(conn: asyncpg.Connection, run_id: int, user: str) -> Run:
    run = await load_run(conn, run_id)
    if run.invoking_user != user:
        raise RunNotFound(run_id)
    return run


async def list_runs(
    conn: asyncpg.Connection, user: str, *, include_dismissed: bool = False
) -> list[Run]:
    rows = await conn.fetch(
        f"""
        select {_RUN_COLUMNS} from query_run
        where invoking_user = $1 and ($2 or dismissed_at is null)
        order by query_run_id
        """,
        user,
        include_dismissed,
    )
    return [_run_from(r) for r in rows]


def columns_path(spool_dir: Path) -> Path:
    return spool_dir / "meta.json"


def read_columns(spool_dir: Path) -> list[str]:
    try:
        return list(json.loads(columns_path(spool_dir).read_text())["columns"])
    except FileNotFoundError as exc:
        raise RunNotFound(f"spool for {spool_dir} is gone") from exc


def caption_for(query_name: str, values: Sequence[str | None]) -> str:
    """``Name(a, b)`` as the Perl GUI labelled a run; None prints as blank."""
    return f"{query_name}({', '.join(v if v is not None else '' for v in values)})"


def ordered_values(
    arg_names: Sequence[str], args: dict[str, str | None]
) -> list[str | None]:
    return [args.get(name) for name in arg_names]


async def start_run(
    conn: asyncpg.Connection,
    pools: PoolRegistry,
    settings: Settings,
    *,
    query_name: str,
    args: dict[str, str | None],
    user: str,
) -> int:
    """Record a run, write its args back to the user's bindings, and schedule it."""
    detail = await catalog.get_query(conn, query_name, pools)
    if not detail.runnable:
        raise RunError(detail.not_runnable_reason or "query cannot run here")
    unknown = sorted(set(args) - set(detail.args))
    if unknown:
        raise RunError(f"query {query_name} has no argument(s) {', '.join(unknown)}")
    open_runs = await conn.fetchval(
        "select count(*) from query_run where invoking_user = $1 and state = any($2)",
        user,
        list(ACTIVE_STATES),
    )
    if open_runs >= settings.max_runs_per_user:
        raise RunLimitExceeded(
            f"{open_runs} queries already running; wait for one to finish or abort it"
        )
    values = ordered_values(detail.args, args)
    invoked_id = await log.query_invoked(conn, query_name, detail.args, values, user)
    if detail.args:
        await bindings.set_bindings(conn, user, dict(zip(detail.args, values)))
    run_id = await conn.fetchval(
        """
        insert into query_run
          (query_name, args, caption, invoking_user, query_invoked_by_dbif_id,
           state, is_select, spool_dir, backend_db)
        values ($1, $2, $3, $4, $5, 'queued', $6, '', $7)
        returning query_run_id
        """,
        query_name,
        json.dumps(dict(zip(detail.args, values))),
        caption_for(query_name, values),
        user,
        invoked_id,
        detail.is_select,
        detail.schema,
    )
    spool_dir = settings.cache_root / "query_runs" / str(run_id)
    spool_dir.mkdir(parents=True, exist_ok=True)
    columns_path(spool_dir).write_text(json.dumps({"columns": detail.columns}))
    await conn.execute(
        "update query_run set spool_dir = $2 where query_run_id = $1",
        run_id,
        str(spool_dir),
    )
    schedule(run_id, pools)
    return int(run_id)


def schedule(run_id: int, pools: PoolRegistry) -> asyncio.Task[None]:
    task = asyncio.create_task(execute_run(run_id, pools), name=f"query_run_{run_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def owner_label() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def _heartbeat(
    ctl: asyncpg.Connection, run_id: int, row_count: int
) -> str | None:
    return await ctl.fetchval(
        """
        update query_run set row_count = $2, last_heartbeat = now()
        where query_run_id = $1
        returning requested_action
        """,
        run_id,
        row_count,
    )


async def _wait_while_paused(ctl: asyncpg.Connection, run_id: int) -> None:
    await ctl.execute(
        "update query_run set state = 'paused', requested_action = null, "
        "last_heartbeat = now() where query_run_id = $1",
        run_id,
    )
    while True:
        await asyncio.sleep(PAUSE_POLL_SECONDS)
        action = await ctl.fetchval(
            "update query_run set last_heartbeat = now() where query_run_id = $1 "
            "returning requested_action",
            run_id,
        )
        if action == "abort":
            raise _Aborted(was_paused=True)
        if action == "resume":
            await ctl.execute(
                "update query_run set state = 'running', requested_action = null "
                "where query_run_id = $1",
                run_id,
            )
            return


async def _after_batch(
    ctl: asyncpg.Connection, run_id: int, writer: RowStoreWriter, rows: list[list[Any]]
) -> None:
    count = await asyncio.to_thread(writer.append_batch, rows)
    action = await _heartbeat(ctl, run_id, count)
    if action == "abort":
        raise _Aborted(was_paused=False)
    if action == "pause":
        await _wait_while_paused(ctl, run_id)


_ROWS_AFFECTED = re.compile(r"(\d+)\s*$")


def rows_affected_from_status(status: str) -> int | None:
    match = _ROWS_AFFECTED.search(status)
    return int(match.group(1)) if match else None


async def _run_postgres(
    ctl: asyncpg.Connection,
    qconn: asyncpg.Connection,
    run: Run,
    sql: str,
    values: list[str | None],
    writer: RowStoreWriter,
) -> int | None:
    """Stream a select into the writer; return rows affected for anything else."""
    tokenized = tokenize(sql, "postgres")
    check_arg_count(tokenized.placeholder_count, len(values))
    statement = await prepare_text_bound(qconn, tokenized.sql)
    if not run.is_select:
        await statement.fetch(*values)  # DML returns no rows; the status has the count
        return rows_affected_from_status(statement.get_statusmsg())
    batch: list[list[Any]] = []
    last_control = time.monotonic()
    async with qconn.transaction():
        async for record in statement.cursor(*values, prefetch=CURSOR_PREFETCH):
            batch.append(list(record))
            due = time.monotonic() - last_control >= CONTROL_INTERVAL_SECONDS
            if len(batch) >= BATCH_ROWS or due:
                await _after_batch(ctl, run.query_run_id, writer, batch)
                batch = []
                last_control = time.monotonic()
    await _after_batch(ctl, run.query_run_id, writer, batch)
    return None


async def _run_mysql(
    ctl: asyncpg.Connection,
    qconn: Any,
    run: Run,
    sql: str,
    values: list[str | None],
    writer: RowStoreWriter,
) -> int | None:
    import aiomysql

    tokenized = tokenize(sql, "mysql")
    check_arg_count(tokenized.placeholder_count, len(values))
    async with qconn.cursor(aiomysql.SSCursor) as cursor:
        await cursor.execute(tokenized.sql, values)
        if not run.is_select:
            return int(cursor.rowcount)
        while True:
            rows = await cursor.fetchmany(BATCH_ROWS)
            if not rows:
                break
            await _after_batch(ctl, run.query_run_id, writer, [list(r) for r in rows])
    await _after_batch(ctl, run.query_run_id, writer, [])
    return None


def _backend_pid(qconn: Any, driver: str) -> int | None:
    if driver == "postgres":
        return int(qconn.get_server_pid())
    thread_id = getattr(qconn, "thread_id", None)
    return int(thread_id()) if callable(thread_id) else None


async def execute_run(run_id: int, pools: PoolRegistry) -> None:
    """The task body: run the query and keep the row up to date."""
    from ...util import db as database

    async with database.pool.acquire() as ctl:
        run = await load_run(ctl, run_id)
        row = await ctl.fetchrow(
            "select query, args, schema from queries where name = $1", run.query_name
        )
        if row is None:
            await _finish(
                ctl, run_id, "error", error=f"query {run.query_name} vanished"
            )
            return
        values = ordered_values(list(row["args"] or []), run.args)
        alias = pools.alias(row["schema"] or "")
        writer: RowStoreWriter | None = None
        try:
            async with pools.connection(alias.name) as qconn:
                await ctl.execute(
                    """
                    update query_run
                    set state = 'running', owner = $2, backend_pid = $3,
                        started_at = now(), last_heartbeat = now()
                    where query_run_id = $1
                    """,
                    run_id,
                    owner_label(),
                    _backend_pid(qconn, alias.driver),
                )
                writer = RowStoreWriter(run.spool_dir)
                runner = _run_postgres if alias.driver == "postgres" else _run_mysql
                affected = await runner(ctl, qconn, run, row["query"], values, writer)
            await _finish(ctl, run_id, "done", rows_affected=affected)
            if run.query_invoked_by_dbif_id is not None:
                await log.query_finished(
                    ctl, run.query_invoked_by_dbif_id, writer.count
                )
        except _Aborted as aborted:
            await _finish(ctl, run_id, "ended" if aborted.was_paused else "aborted")
        except asyncio.CancelledError:
            await _finish(ctl, run_id, "aborted", error="API process shut down")
            raise
        except Exception as exc:  # noqa: BLE001 - every failure must land on the row
            if await _abort_requested(ctl, run_id):
                await _finish(ctl, run_id, "aborted")
            else:
                logger.exception("query run %s failed", run_id)
                await _finish(ctl, run_id, "error", error=str(exc))
        finally:
            if writer is not None:
                writer.close()


async def _abort_requested(ctl: asyncpg.Connection, run_id: int) -> bool:
    action = await ctl.fetchval(
        "select requested_action from query_run where query_run_id = $1", run_id
    )
    return action == "abort"


async def _finish(
    ctl: asyncpg.Connection,
    run_id: int,
    state: str,
    *,
    error: str | None = None,
    rows_affected: int | None = None,
) -> None:
    await ctl.execute(
        """
        update query_run
        set state = $2, error_text = $3, rows_affected = coalesce($4, rows_affected),
            requested_action = null, finished_at = now(), last_heartbeat = now()
        where query_run_id = $1
        """,
        run_id,
        state,
        error,
        rows_affected,
    )


# --- control requests, from any process -------------------------------------


async def request_pause(conn: asyncpg.Connection, run: Run) -> None:
    if run.state != "running":
        raise BadRunState("can only pause a running query")
    await conn.execute(
        "update query_run set requested_action = 'pause' where query_run_id = $1",
        run.query_run_id,
    )


async def request_resume(conn: asyncpg.Connection, run: Run) -> None:
    if run.state == "running" and run.requested_action == "pause":
        # The pause has not taken effect yet; just withdraw it.
        await conn.execute(
            "update query_run set requested_action = null where query_run_id = $1",
            run.query_run_id,
        )
        return
    if run.state != "paused":
        raise BadRunState("can only resume a paused query")
    await conn.execute(
        "update query_run set requested_action = 'resume' where query_run_id = $1",
        run.query_run_id,
    )


async def request_abort(
    conn: asyncpg.Connection, pools: PoolRegistry, run: Run
) -> None:
    if not run.active:
        raise BadRunState("query is not running")
    await conn.execute(
        "update query_run set requested_action = 'abort' where query_run_id = $1",
        run.query_run_id,
    )
    if run.backend_pid is None or run.backend_db is None:
        return
    try:
        await _cancel_backend(pools, run.backend_db, run.backend_pid)
    except Exception:  # noqa: BLE001 - the flag alone still stops it at the next batch
        logger.exception("could not cancel backend for query run %s", run.query_run_id)


async def _cancel_backend(
    pools: PoolRegistry, alias_name: str, backend_pid: int
) -> None:
    alias = pools.alias(alias_name)
    async with pools.connection(alias_name) as qconn:
        if alias.driver == "postgres":
            await qconn.fetchval("select pg_cancel_backend($1)", backend_pid)
        else:
            async with qconn.cursor() as cursor:
                await cursor.execute("kill query %s", (backend_pid,))


async def dismiss(conn: asyncpg.Connection, run: Run) -> None:
    if run.active:
        raise BadRunState("abort the query before dismissing it")
    await conn.execute(
        "update query_run set dismissed_at = now() where query_run_id = $1",
        run.query_run_id,
    )


# --- reading results ----------------------------------------------------------


def _view_for(run: Run) -> FilteredView | None:
    """The materialised filtered view for the run's filter, if built."""
    spec = normalise(run.filter)
    if not spec:
        return None
    return existing_view(run.spool_dir, filter_key(spec, run.row_count))


async def filtered_view(run: Run) -> FilteredView | None:
    """Build (in a thread) or reuse the filtered view for the run's filter."""
    spec = normalise(run.filter)
    if not spec:
        return None
    view = _view_for(run)
    if view is not None:
        return view
    columns = read_columns(run.spool_dir)
    return await asyncio.to_thread(
        build_view, run.spool_dir, columns, spec, available=run.row_count
    )


async def page(run: Run, first: int, n: int, *, filtered: bool) -> tuple[Page, int]:
    """Rows ``first..first+n`` of the run, filtered or not, with the total."""
    if filtered:
        view = await filtered_view(run)
        if view is not None:
            reader = RowStoreReader(run.spool_dir, view.name)
            return (
                await asyncio.to_thread(reader.rows, first, n, available=view.count),
                view.count,
            )
    reader = RowStoreReader(run.spool_dir)
    return (
        await asyncio.to_thread(reader.rows, first, n, available=run.row_count),
        run.row_count,
    )


async def set_filter(
    conn: asyncpg.Connection, run: Run, filter_spec: Filter | None, view_filtered: bool
) -> None:
    spec = normalise(filter_spec)
    columns = read_columns(run.spool_dir)
    unknown = sorted(set(spec) - set(columns))
    if unknown:
        raise RunError(f"no such column(s): {', '.join(unknown)}")
    await conn.execute(
        "update query_run set filter = $2, view_filtered = $3 where query_run_id = $1",
        run.query_run_id,
        json.dumps(spec) if spec else None,
        view_filtered and bool(spec),
    )


def remove_spool(spool_dir: Path) -> None:
    shutil.rmtree(spool_dir, ignore_errors=True)


async def cancel_all_runs() -> None:
    """Cancel this process's run tasks; each marks its row aborted on the way out."""
    tasks = list(_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
