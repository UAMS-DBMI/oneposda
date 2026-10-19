"""Starting a background operation: a port of ``StartSubprocess``.

Every launch source (workflow button, result table, result row, compare
timepoints, uploaded spreadsheet, background query) ends in the same
sequence, on one connection in one transaction:

1. unless the launch came from an uploaded spreadsheet, write a CSV that
   records the operation, its argument values and the input rows (so the
   launch can be re-run from the Upload page) and import it;
2. ``spreadsheet_uploaded``; 3. ``subprocess_invocation``;
4. the rendered input lines imported as the worker's stdin file;
5. ``work`` with the operation's priority queue; commit;
6. LPUSH the work id on Redis.

The CSV is written with the ``csv`` module (fields per column, quoting), so
unlike the Perl one it reads back cleanly as a named spreadsheet.
"""

import csv
import logging
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg

from .. import workqueue
from ..files import ingest
from ..settings import Settings
from .catalog import Operation
from .placeholders import expand_command, render_input_lines

logger = logging.getLogger(__name__)

CSV_IMPORT_COMMENT = "ABC launch spreadsheet"
INPUT_IMPORT_COMMENT = "ABC launch input lines"


@dataclass(frozen=True)
class LaunchPlan:
    operation: Operation
    args: dict[str, str]
    rows: Sequence[Mapping[str, object]]
    button_name: str
    spreadsheet_file_id: int | None = None  # set when launched from an upload
    query_invoked_by_dbif_id: int | None = None
    input_lines: list[str] = field(default_factory=list)

    @property
    def expanded_command(self) -> str:
        return expand_command(self.operation.command_line, self.args)


@dataclass(frozen=True)
class LaunchResult:
    subprocess_invocation_id: int
    work_id: int
    queue_name: str
    pending_work: int
    spreadsheet_file_id: int
    input_file_id: int
    command_line: str


def make_plan(
    operation: Operation,
    args: Mapping[str, str],
    rows: Sequence[Mapping[str, object]],
    *,
    button_name: str,
    spreadsheet_file_id: int | None = None,
    query_invoked_by_dbif_id: int | None = None,
) -> LaunchPlan:
    return LaunchPlan(
        operation=operation,
        args={name: args.get(name, "") for name in operation.args},
        rows=rows,
        button_name=button_name,
        spreadsheet_file_id=spreadsheet_file_id,
        query_invoked_by_dbif_id=query_invoked_by_dbif_id,
        input_lines=render_input_lines(
            operation.input_line_format, operation.fields, rows
        ),
    )


def write_launch_csv(plan: LaunchPlan, directory: Path) -> Path:
    """The re-runnable record of this launch: fields, Operation, args."""
    operation = plan.operation
    arg_names = sorted(plan.args)
    handle = tempfile.NamedTemporaryFile(
        "w", dir=directory, prefix="launch-", suffix=".csv", delete=False, newline=""
    )
    with handle:
        writer = csv.writer(handle)
        writer.writerow([*operation.fields, "Operation", *arg_names])
        rows = list(plan.rows) or [{}]
        for index, row in enumerate(rows):
            cells = [
                "" if row.get(f) is None else str(row.get(f)) for f in operation.fields
            ]
            if index == 0:
                cells += [operation.operation_name, *(plan.args[a] for a in arg_names)]
            else:
                cells += [""] * (1 + len(arg_names))
            writer.writerow(cells)
    return Path(handle.name)


def write_input_file(plan: LaunchPlan, directory: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(
        "w", dir=directory, prefix="input-", suffix=".txt", delete=False
    )
    with handle:
        for line in plan.input_lines:
            handle.write(f"{line}\n")
    return Path(handle.name)


async def launch(
    conn: asyncpg.Connection,
    queue: workqueue.WorkQueue,
    settings: Settings,
    plan: LaunchPlan,
    *,
    user: str,
) -> LaunchResult:
    storage = ingest.Storage(settings.storage_root_id, settings.storage_root_path)
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    priority = plan.operation.worker_priority
    name = workqueue.queue_name(priority)
    async with conn.transaction():
        spreadsheet_file_id = plan.spreadsheet_file_id
        if spreadsheet_file_id is None:
            csv_path = write_launch_csv(plan, settings.temp_path)
            spreadsheet_file_id = (
                await ingest.import_local_file(
                    conn, csv_path, storage, comment=CSV_IMPORT_COMMENT
                )
            ).file_id
            csv_path.unlink(missing_ok=True)
        spreadsheet_uploaded_id = await conn.fetchval(
            """
            insert into spreadsheet_uploaded
              (time_uploaded, is_executable, uploading_user, file_id_in_posda, number_rows)
            values (now(), true, $1, $2, $3)
            returning spreadsheet_uploaded_id
            """,
            user,
            spreadsheet_file_id,
            len(plan.input_lines),
        )
        command_line = plan.expanded_command
        invocation_id = await conn.fetchval(
            """
            insert into subprocess_invocation
              (from_spreadsheet, from_button, query_invoked_by_dbif_id, button_name,
               command_line, spreadsheet_uploaded_id, invoking_user, when_invoked,
               operation_name)
            values ($1, $2, $3, $4, $5, $6, $7, now(), $8)
            returning subprocess_invocation_id
            """,
            plan.spreadsheet_file_id is not None,
            plan.spreadsheet_file_id is None,
            plan.query_invoked_by_dbif_id,
            plan.button_name,
            command_line,
            spreadsheet_uploaded_id,
            user,
            plan.operation.operation_name,
        )
        input_path = write_input_file(plan, settings.temp_path)
        input_file_id = (
            await ingest.import_local_file(
                conn, input_path, storage, comment=INPUT_IMPORT_COMMENT
            )
        ).file_id
        input_path.unlink(missing_ok=True)
        work_id = await conn.fetchval(
            """
            insert into work (subprocess_invocation_id, input_file_id, background_queue_name)
            values ($1, $2, $3)
            returning work_id
            """,
            invocation_id,
            input_file_id,
            name,
        )
    try:
        workqueue.push_work(queue, name, int(work_id))
    except Exception as exc:
        logger.exception("work %s committed but not queued on %s", work_id, name)
        raise WorkNotQueued(int(work_id), int(invocation_id), name) from exc
    return LaunchResult(
        subprocess_invocation_id=int(invocation_id),
        work_id=int(work_id),
        queue_name=name,
        pending_work=await workqueue.pending_work_count(conn),
        spreadsheet_file_id=int(spreadsheet_file_id),
        input_file_id=int(input_file_id),
        command_line=command_line,
    )


class WorkNotQueued(RuntimeError):
    """The work row exists but Redis refused the push; it can be re-queued."""

    def __init__(self, work_id: int, subprocess_invocation_id: int, queue: str) -> None:
        super().__init__(
            f"work {work_id} (subprocess_invocation {subprocess_invocation_id}) was "
            f"recorded but could not be queued on {queue}"
        )
        self.work_id = work_id
        self.subprocess_invocation_id = subprocess_invocation_id
        self.queue = queue
