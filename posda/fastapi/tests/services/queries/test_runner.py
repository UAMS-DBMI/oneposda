"""The runner's execution engine against the dev database.

``ctl`` is the rollback fixture connection (holds the query_run row); the
query itself runs on a second connection, as it does in the API.
"""

import asyncio
import json
from pathlib import Path

import asyncpg
import pytest

from papi.services.queries import runner
from papi.services.queries.codecs import install_text_codecs
from papi.services.queries.rowstore import RowStoreReader, RowStoreWriter


@pytest.fixture
async def qconn():
    connection = await asyncpg.connect()
    await install_text_codecs(connection)
    try:
        yield connection
    finally:
        await connection.close()


async def insert_run(ctl, tmp_path: Path, *, is_select: bool = True) -> runner.Run:
    run_id = await ctl.fetchval(
        """
        insert into query_run (query_name, args, caption, invoking_user, state,
                               is_select, spool_dir, backend_db)
        values ('Test', '{}', 'Test()', 'runner-test', 'running', $1, $2, 'posda_files')
        returning query_run_id
        """,
        is_select,
        str(tmp_path),
    )
    runner.columns_path(tmp_path).write_text(json.dumps({"columns": ["n", "label"]}))
    return await runner.load_run(ctl, run_id)


async def test_select_streams_rows_in_batches(conn, qconn, tmp_path: Path) -> None:
    run = await insert_run(conn, tmp_path)
    writer = RowStoreWriter(tmp_path)
    n = runner.BATCH_ROWS * 2 + 5
    affected = await runner._run_postgres(
        conn,
        qconn,
        run,
        "select g as n, 'row ' || g as label from generate_series(1, ?::int) g",
        [str(n)],
        writer,
    )
    writer.close()
    assert affected is None
    assert writer.count == n
    assert (
        await conn.fetchval(
            "select row_count from query_run where query_run_id = $1", run.query_run_id
        )
        == n
    )
    page = RowStoreReader(tmp_path).rows(n - 2, 5, available=n)
    assert page.rows == [[n - 1, f"row {n - 1}"], [n, f"row {n}"]]


async def test_abort_flag_stops_between_batches(conn, qconn, tmp_path: Path) -> None:
    run = await insert_run(conn, tmp_path)
    await conn.execute(
        "update query_run set requested_action = 'abort' where query_run_id = $1",
        run.query_run_id,
    )
    writer = RowStoreWriter(tmp_path)
    with pytest.raises(runner._Aborted) as aborted:
        await runner._run_postgres(
            conn,
            qconn,
            run,
            "select g as n, 'x' as label from generate_series(1, 5000) g",
            [],
            writer,
        )
    writer.close()
    assert aborted.value.was_paused is False
    assert writer.count == runner.BATCH_ROWS


async def test_pause_waits_for_resume(conn, qconn, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "PAUSE_POLL_SECONDS", 0.05)
    run = await insert_run(conn, tmp_path)
    await conn.execute(
        "update query_run set requested_action = 'pause' where query_run_id = $1",
        run.query_run_id,
    )
    writer = RowStoreWriter(tmp_path)

    async def resume_soon() -> None:
        # Wait until the runner has recorded the pause, then ask it to go on.
        for _ in range(100):
            await asyncio.sleep(0.05)
            state = await conn.fetchval(
                "select state from query_run where query_run_id = $1", run.query_run_id
            )
            if state == "paused":
                break
        await conn.execute(
            "update query_run set requested_action = 'resume' where query_run_id = $1",
            run.query_run_id,
        )

    resumer = asyncio.create_task(resume_soon())
    await runner._run_postgres(
        conn,
        qconn,
        run,
        "select g as n, 'x' as label from generate_series(1, 2500) g",
        [],
        writer,
    )
    await resumer
    writer.close()
    assert writer.count == 2500
    row = await conn.fetchrow(
        "select state, requested_action from query_run where query_run_id = $1",
        run.query_run_id,
    )
    assert (row["state"], row["requested_action"]) == ("running", None)


async def test_non_select_reports_rows_affected(conn, qconn, tmp_path: Path) -> None:
    run = await insert_run(conn, tmp_path, is_select=False)
    writer = RowStoreWriter(tmp_path)
    async with qconn.transaction():
        await qconn.execute("create temp table runner_scratch(v int)")
        await qconn.execute("insert into runner_scratch values (1), (2), (3)")
        affected = await runner._run_postgres(
            conn,
            qconn,
            run,
            "update runner_scratch set v = v + ? where v > ?",
            ["10", "1"],
            writer,
        )
    writer.close()
    assert affected == 2
    assert writer.count == 0


async def test_caption_and_values_follow_arg_order() -> None:
    assert runner.caption_for("Q", ["1", None, "x"]) == "Q(1, , x)"
    assert runner.ordered_values(["b", "a"], {"a": "1", "b": None}) == [None, "1"]
    assert runner.rows_affected_from_status("UPDATE 7") == 7
    assert runner.rows_affected_from_status("INSERT 0 3") == 3
    assert runner.rows_affected_from_status("CREATE TABLE") is None
