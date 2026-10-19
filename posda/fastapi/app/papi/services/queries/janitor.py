"""Housekeeping for query runs: lost-run detection and spool retention.

Every API process starts one janitor task. On each tick the task tries a
Postgres advisory lock so only one process does the work, then:

- marks ``running``/``paused`` runs whose heartbeat is older than
  ``LOST_AFTER`` as ``lost`` (their rows so far stay pageable), and
  ``queued`` runs that never started as ``lost`` too;
- deletes the spool directory of runs finished longer ago than the
  retention period, or dismissed more than a day ago.
"""

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

import asyncpg

from ..settings import Settings
from .runner import remove_spool

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
LOST_AFTER = timedelta(minutes=2)
QUEUED_LOST_AFTER = timedelta(minutes=10)
DISMISSED_RETENTION = timedelta(days=1)
ADVISORY_LOCK_KEY = 0x5157_5259_4A41  # "QWRYJA" - arbitrary, unique to this job


async def mark_lost_runs(conn: asyncpg.Connection) -> int:
    """Flag runs whose executing process has stopped heartbeating."""
    status = await conn.execute(
        """
        update query_run
        set state = 'lost', finished_at = now(),
            error_text = coalesce(error_text, 'the API process running this query went away')
        where (state in ('running', 'paused') and last_heartbeat < now() - $1::interval)
           or (state = 'queued' and created_at < now() - $2::interval)
        """,
        LOST_AFTER,
        QUEUED_LOST_AFTER,
    )
    return int(status.rsplit(" ", 1)[-1])


async def expired_spools(
    conn: asyncpg.Connection, settings: Settings
) -> list[tuple[int, Path]]:
    rows = await conn.fetch(
        """
        select query_run_id, spool_dir from query_run
        where spool_dir <> ''
          and state not in ('queued', 'running', 'paused')
          and (coalesce(finished_at, created_at) < now() - $1::interval
               or dismissed_at < now() - $2::interval)
        """,
        timedelta(days=settings.run_retention_days),
        DISMISSED_RETENTION,
    )
    return [(int(r["query_run_id"]), Path(r["spool_dir"])) for r in rows]


async def remove_expired_spools(conn: asyncpg.Connection, settings: Settings) -> int:
    """Delete expired spool directories and blank their path on the row."""
    removed = 0
    for run_id, spool_dir in await expired_spools(conn, settings):
        if spool_dir.exists():
            await asyncio.to_thread(remove_spool, spool_dir)
        await conn.execute(
            "update query_run set spool_dir = '' where query_run_id = $1", run_id
        )
        removed += 1
    return removed


async def tick(conn: asyncpg.Connection, settings: Settings) -> bool:
    """One pass; returns False when another process holds the lock."""
    if not await conn.fetchval("select pg_try_advisory_lock($1)", ADVISORY_LOCK_KEY):
        return False
    try:
        lost = await mark_lost_runs(conn)
        removed = await remove_expired_spools(conn, settings)
        if lost or removed:
            logger.info("query run janitor: %d lost, %d spools removed", lost, removed)
    finally:
        await conn.fetchval("select pg_advisory_unlock($1)", ADVISORY_LOCK_KEY)
    return True


async def run_forever(
    settings: Settings, *, tick_seconds: float = TICK_SECONDS
) -> None:
    from ...util import db as database

    while True:
        try:
            async with database.pool.acquire() as conn:
                await tick(conn, settings)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - keep the janitor alive, report the pass
            logger.exception("query run janitor pass failed")
        await asyncio.sleep(tick_seconds)
