import asyncpg
import pytest

from papi.services import background_jobs


async def test_list_jobs_filters_by_status_and_window(conn) -> None:
    invocation_id = await conn.fetchval(
        "insert into subprocess_invocation (invoking_user, when_invoked, command_line) "
        "values ('bg-test', now() - interval '1 minute', 'x.pl') returning subprocess_invocation_id"
    )
    await conn.execute(
        "insert into work (subprocess_invocation_id, status) values ($1, 'errored')", invocation_id
    )
    errored = await background_jobs.list_jobs(conn, mode="errored", in_last="1 hour")
    assert any(j.subprocess_invocation_id == invocation_id for j in errored.jobs)
    assert errored.total >= 1
    finished = await background_jobs.list_jobs(conn, mode="finished", in_last="1 hour")
    assert all(j.subprocess_invocation_id != invocation_id for j in finished.jobs)
    everything = await background_jobs.list_jobs(conn, mode="all", in_last=None)
    assert everything.total >= errored.total


async def test_bad_interval_is_a_data_error(conn) -> None:
    with pytest.raises(asyncpg.DataError):
        await background_jobs.list_jobs(conn, mode="all", in_last="twelve fortnights")
