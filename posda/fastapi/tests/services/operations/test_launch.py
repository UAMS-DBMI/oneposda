"""Launching an operation end to end on the dev database (rolled back)."""

import csv
from pathlib import Path

import pytest

from papi.services import workqueue
from papi.services.operations import catalog, launch
from papi.services.settings import Settings


class FakeQueue:
    def __init__(self, fail: bool = False) -> None:
        self.pushed: list[tuple[str, str]] = []
        self.fail = fail

    def lpush(self, name: str, *values: str) -> int:
        if self.fail:
            raise ConnectionError("redis down")
        self.pushed.extend((name, v) for v in values)
        return len(self.pushed)


def settings(tmp_path: Path) -> Settings:
    return Settings(
        cache_root=tmp_path / "cache",
        database_config=tmp_path / "databases.json",
        posdatools_root=tmp_path,
        storage_root_id=3,
        storage_root_path=tmp_path / "created",
        temp_path=tmp_path / "temp",
        redis_host="redis",
        run_retention_days=7,
        query_timeout_ms=0,
        max_runs_per_user=5,
    )


async def stored_text(conn, file_id: int, root: Path) -> str:
    rel = await conn.fetchval(
        "select rel_path from file_location where file_id = $1", file_id
    )
    return (root / rel).read_text()


async def test_launch_records_everything_and_queues_the_work(
    conn, tmp_path: Path
) -> None:
    operation = await catalog.get_operation(conn, "AddFilesToTimepoint")
    plan = launch.make_plan(
        operation,
        {"activity_id": "1", "comment": "hello, world", "notify": "abc-test"},
        [{"file_id": 10}, {"file_id": 11}],
        button_name="Add Files",
        query_invoked_by_dbif_id=None,
    )
    assert plan.input_lines == ["10", "11"]
    assert (
        plan.expanded_command
        == 'AddFilesToTimepoint.pl <?bkgrnd_id?> 1 "hello, world" abc-test'
    )

    queue = FakeQueue()
    result = await launch.launch(conn, queue, settings(tmp_path), plan, user="abc-test")

    assert queue.pushed == [("work_queue_0", str(result.work_id))]
    invocation = await conn.fetchrow(
        "select * from subprocess_invocation where subprocess_invocation_id = $1",
        result.subprocess_invocation_id,
    )
    assert invocation["from_button"] is True and invocation["from_spreadsheet"] is False
    assert invocation["command_line"] == plan.expanded_command
    assert invocation["operation_name"] == "AddFilesToTimepoint"
    assert invocation["button_name"] == "Add Files"
    uploaded = await conn.fetchrow(
        "select * from spreadsheet_uploaded where spreadsheet_uploaded_id = $1",
        invocation["spreadsheet_uploaded_id"],
    )
    assert uploaded["number_rows"] == 2 and uploaded["uploading_user"] == "abc-test"
    work = await conn.fetchrow("select * from work where work_id = $1", result.work_id)
    assert work["background_queue_name"] == "work_queue_0"
    assert work["input_file_id"] == result.input_file_id

    root = settings(tmp_path).storage_root_path
    assert await stored_text(conn, result.input_file_id, root) == "10\n11\n"
    sheet = list(
        csv.reader(
            (await stored_text(conn, result.spreadsheet_file_id, root)).splitlines()
        )
    )
    assert sheet[0] == ["file_id", "Operation", "activity_id", "comment", "notify"]
    assert sheet[1] == ["10", "AddFilesToTimepoint", "1", "hello, world", "abc-test"]
    assert sheet[2] == ["11", "", "", "", ""]
    assert not list(settings(tmp_path).temp_path.iterdir())  # temp files cleaned up


async def test_launch_without_input_rows_writes_one_row_csv(
    conn, tmp_path: Path
) -> None:
    operation = await catalog.get_operation(conn, "AnalyzeSeriesDuplicatesForTimepoint")
    plan = launch.make_plan(
        operation, {"activity_id": "1", "notify": "u"}, [], button_name="x"
    )
    assert plan.input_lines == []
    result = await launch.launch(conn, FakeQueue(), settings(tmp_path), plan, user="u")
    root = settings(tmp_path).storage_root_path
    # An empty input file has a well-known digest that usually already exists.
    digest = await conn.fetchval(
        "select digest from file where file_id = $1", result.input_file_id
    )
    assert digest == "d41d8cd98f00b204e9800998ecf8427e"
    sheet = list(
        csv.reader(
            (await stored_text(conn, result.spreadsheet_file_id, root)).splitlines()
        )
    )
    assert sheet == [
        ["Operation", "activity_id", "notify"],
        ["AnalyzeSeriesDuplicatesForTimepoint", "1", "u"],
    ]


async def test_launch_from_uploaded_spreadsheet_reuses_its_file(
    conn, tmp_path: Path
) -> None:
    operation = await catalog.get_operation(conn, "AddFilesToTimepoint")
    existing = await conn.fetchval("select min(file_id) from file")
    plan = launch.make_plan(
        operation,
        {"activity_id": "1", "comment": "", "notify": "u"},
        [{"file_id": 1}],
        button_name="upload",
        spreadsheet_file_id=existing,
    )
    result = await launch.launch(conn, FakeQueue(), settings(tmp_path), plan, user="u")
    assert result.spreadsheet_file_id == existing
    invocation = await conn.fetchrow(
        "select from_spreadsheet, from_button from subprocess_invocation where subprocess_invocation_id = $1",
        result.subprocess_invocation_id,
    )
    assert invocation["from_spreadsheet"] is True and invocation["from_button"] is False


async def test_queue_failure_after_commit_is_reported_with_ids(
    conn, tmp_path: Path
) -> None:
    operation = await catalog.get_operation(conn, "AnalyzeSeriesDuplicatesForTimepoint")
    plan = launch.make_plan(
        operation, {"activity_id": "1", "notify": "u"}, [], button_name="x"
    )
    with pytest.raises(launch.WorkNotQueued) as failure:
        await launch.launch(
            conn, FakeQueue(fail=True), settings(tmp_path), plan, user="u"
        )
    assert failure.value.queue == "work_queue_0"
    assert (
        await conn.fetchval(
            "select count(*) from work where work_id = $1", failure.value.work_id
        )
        == 1
    )


async def test_pending_work_count_counts_unfinished(conn) -> None:
    before = await workqueue.pending_work_count(conn)
    invocation_id = await conn.fetchval(
        "insert into subprocess_invocation (invoking_user, when_invoked) values ('u', now()) "
        "returning subprocess_invocation_id"
    )
    await conn.execute(
        "insert into work (subprocess_invocation_id, status) values ($1, 'queued')",
        invocation_id,
    )
    assert await workqueue.pending_work_count(conn) == before + 1
