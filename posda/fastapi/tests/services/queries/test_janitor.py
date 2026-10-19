from datetime import timedelta
from pathlib import Path

from papi.services.queries import janitor
from papi.services.settings import Settings


def settings(tmp_path: Path) -> Settings:
    return Settings(
        cache_root=tmp_path,
        database_config=tmp_path / "databases.json",
        redis_host="redis",
        run_retention_days=7,
        query_timeout_ms=0,
        max_runs_per_user=5,
    )


async def insert_run(
    conn,
    *,
    state: str,
    spool_dir: Path,
    heartbeat_age: timedelta,
    finished_age: timedelta | None = None,
) -> int:
    return await conn.fetchval(
        """
        insert into query_run (query_name, args, caption, invoking_user, state,
                               spool_dir, last_heartbeat, created_at, finished_at)
        values ('T', '{}', 'T()', 'janitor-test', $1, $2, now() - $3::interval,
                now() - $3::interval, case when $4::interval is null then null
                                          else now() - $4::interval end)
        returning query_run_id
        """,
        state,
        str(spool_dir),
        heartbeat_age,
        finished_age,
    )


async def test_stale_running_runs_are_marked_lost(conn, tmp_path: Path) -> None:
    stale = await insert_run(
        conn, state="running", spool_dir=tmp_path, heartbeat_age=timedelta(minutes=5)
    )
    fresh = await insert_run(
        conn, state="running", spool_dir=tmp_path, heartbeat_age=timedelta(seconds=5)
    )
    assert await janitor.mark_lost_runs(conn) >= 1
    states = {
        r["query_run_id"]: r["state"]
        for r in await conn.fetch(
            "select query_run_id, state from query_run where query_run_id = any($1)",
            [stale, fresh],
        )
    }
    assert states[stale] == "lost"
    assert states[fresh] == "running"


async def test_expired_spools_are_removed(conn, tmp_path: Path) -> None:
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    (old_dir / "rows.jsonl").write_text("[1]\n")
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    old = await insert_run(
        conn,
        state="done",
        spool_dir=old_dir,
        heartbeat_age=timedelta(days=9),
        finished_age=timedelta(days=9),
    )
    new = await insert_run(
        conn,
        state="done",
        spool_dir=new_dir,
        heartbeat_age=timedelta(days=1),
        finished_age=timedelta(days=1),
    )

    await janitor.remove_expired_spools(conn, settings(tmp_path))

    assert not old_dir.exists()
    assert new_dir.exists()
    assert (
        await conn.fetchval(
            "select spool_dir from query_run where query_run_id = $1", old
        )
        == ""
    )
    assert await conn.fetchval(
        "select spool_dir from query_run where query_run_id = $1", new
    ) == str(new_dir)


async def test_tick_takes_the_advisory_lock(conn, tmp_path: Path) -> None:
    assert await janitor.tick(conn, settings(tmp_path)) is True
