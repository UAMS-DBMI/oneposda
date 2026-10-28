"""Queue a spreadsheet operation as a background process, the way the GUI does.

Pressing "Start" in the Posda GUI (``Posda::NewerProcessPopup::StartSubprocess``)
performs this sequence, and so does :func:`launch`:

1. write a CSV recording the operation, its argument values and the input
   lines, and import it into Posda so the launch can be re-run from the
   Upload page;
2. insert ``spreadsheet_uploaded``;
3. insert ``subprocess_invocation`` (``from_button``, the command line still
   holding ``<?bkgrnd_id?>``, which the worker substitutes);
4. write the input lines to a file and import it: that file becomes the
   worker's stdin for the script;
5. insert ``work`` naming the operation's priority queue; commit;
6. LPUSH the work id on that Redis list.

Steps 2, 3 and 5 run in one transaction so a failure leaves no half-launched
rows behind. The pure helpers (placeholder parsing, parameter resolution,
command expansion) have no database or network dependencies so they can be
tested and reused on their own.
"""

from __future__ import annotations

import csv
import io
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BUTTON_NAME = "start-background-process"
LAUNCH_CSV_COMMENT = "start-background-process launch spreadsheet"
INPUT_FILE_COMMENT = "start-background-process input lines"
BACKGROUND_PROCESS = "background_process"

_PLACEHOLDER = re.compile(r"<([^<>]+)>")
_META = re.compile(r"^\?(.*)\?$")

ImportFile = Callable[[str, str], int]
PushWork = Callable[[str, int], None]


class LaunchError(Exception):
    """Base class for everything this module refuses to do."""


class UnknownOperationError(LaunchError):
    def __init__(self, operation_name: str) -> None:
        super().__init__(f"no spreadsheet operation named {operation_name!r}")
        self.operation_name = operation_name


class OperationNotLaunchableError(LaunchError):
    """The operation exists but is not a (current) background process."""


class ParameterError(LaunchError):
    """Supplied parameters do not match what the operation's command needs."""


class InputError(LaunchError):
    """The input rows do not fit the operation's input line format."""


class WorkNotQueuedError(LaunchError):
    """The work row is committed but Redis refused the push; it can be re-queued."""

    def __init__(self, work_id: int, subprocess_invocation_id: int, queue: str) -> None:
        super().__init__(
            f"work {work_id} (subprocess_invocation {subprocess_invocation_id}) was "
            f"recorded but could not be queued on {queue}"
        )
        self.work_id = work_id
        self.subprocess_invocation_id = subprocess_invocation_id
        self.queue = queue


def _unique(names: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def parse_placeholders(text: str | None) -> tuple[list[str], list[str]]:
    """Split ``<name>`` placeholders into (args, meta_args).

    ``<name>`` is something the user supplies; ``<?name?>`` is filled in by
    the worker (``<?bkgrnd_id?>`` becomes the subprocess_invocation_id).
    Mirrors ``BuildFieldsAndArgs`` in the Perl GUI, reporting duplicates once.
    """
    args: list[str] = []
    meta: list[str] = []
    for token in _PLACEHOLDER.findall(text or ""):
        match = _META.match(token)
        if match:
            meta.append(match.group(1))
        else:
            args.append(token)
    return _unique(args), _unique(meta)


def expand_command(command_line: str, values: Mapping[str, str]) -> str:
    """Substitute every ``<arg>`` in ``values``; meta args are left alone.

    The Perl substitution lacked ``/g`` and so only replaced the first
    occurrence of a repeated argument; replacing all of them is the intent.
    """
    expanded = command_line
    for name, value in values.items():
        expanded = expanded.replace(f"<{name}>", value)
    return expanded


@dataclass(frozen=True)
class Operation:
    """One row of ``spreadsheet_operation``, with its placeholders parsed."""

    operation_name: str
    command_line: str
    operation_type: str | None
    input_line_format: str | None
    tags: list[str] = field(default_factory=list)
    outdated: bool = False
    worker_priority: int = 0

    @property
    def args(self) -> list[str]:
        return parse_placeholders(self.command_line)[0]

    @property
    def meta_args(self) -> list[str]:
        return parse_placeholders(self.command_line)[1]

    @property
    def fields(self) -> list[str]:
        return parse_placeholders(self.input_line_format)[0]

    @property
    def queue_name(self) -> str:
        return f"work_queue_{self.worker_priority}"

    @property
    def program(self) -> str:
        head = self.command_line.strip().split(None, 1)
        return head[0] if head else ""

    @property
    def is_background_process(self) -> bool:
        return self.operation_type == BACKGROUND_PROCESS


_OPERATION_COLUMNS = """
    operation_name, command_line, operation_type, input_line_format,
    tags, outdated, worker_priority
"""


def _operation_from_row(row: Sequence[Any]) -> Operation:
    name, command_line, op_type, line_format, tags, outdated, priority = row
    return Operation(
        operation_name=name,
        command_line=command_line or "",
        operation_type=op_type,
        input_line_format=line_format,
        tags=list(tags or []),
        outdated=bool(outdated),
        worker_priority=int(priority or 0),
    )


def load_operation(conn: Any, operation_name: str) -> Operation:
    """Fetch one operation from ``spreadsheet_operation`` (posda_files)."""
    with conn.cursor() as cur:
        cur.execute(
            f"select {_OPERATION_COLUMNS} from spreadsheet_operation "
            "where operation_name = %s",
            [operation_name],
        )
        row = cur.fetchone()
    if row is None:
        raise UnknownOperationError(operation_name)
    return _operation_from_row(row)


def list_operations(conn: Any, tag: str | None = None) -> list[Operation]:
    """All operations, optionally only those carrying ``tag``, by name."""
    sql = f"select {_OPERATION_COLUMNS} from spreadsheet_operation"
    params: list[Any] = []
    if tag is not None:
        sql += " where %s = any(tags)"
        params.append(tag)
    sql += " order by operation_name"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_operation_from_row(row) for row in rows]


def check_launchable(operation: Operation, allow_outdated: bool = False) -> None:
    """Refuse what the GUI's process popup refuses (plus outdated rows)."""
    if not operation.is_background_process:
        raise OperationNotLaunchableError(
            f"{operation.operation_name} has operation_type "
            f"{operation.operation_type!r}; only {BACKGROUND_PROCESS!r} "
            "operations run through the background worker"
        )
    if operation.outdated and not allow_outdated:
        raise OperationNotLaunchableError(
            f"{operation.operation_name} is marked outdated "
            "(pass --allow-outdated to launch it anyway)"
        )


def resolve_parameters(
    operation: Operation, supplied: Mapping[str, str]
) -> dict[str, str]:
    """Match supplied values to the command's ``<args>``, in command order.

    Every argument must be supplied (an empty string is a valid value), and
    nothing may be supplied that the command does not use. Values may not
    contain newlines: the command line is one shell line.
    """
    missing = [name for name in operation.args if name not in supplied]
    unknown = [name for name in supplied if name not in operation.args]
    problems = []
    if missing:
        problems.append(f"missing parameters: {', '.join(missing)}")
    if unknown:
        problems.append(f"unknown parameters: {', '.join(unknown)}")
    if problems:
        problems.append(
            f"{operation.operation_name} takes: {', '.join(operation.args)}"
        )
        raise ParameterError("; ".join(problems))
    for name in operation.args:
        if "\n" in supplied[name] or "\r" in supplied[name]:
            raise ParameterError(f"parameter {name} may not contain a newline")
    return {name: supplied[name] for name in operation.args}


def read_input_lines(text: str) -> list[str]:
    """Input lines as the worker will see them: one per line, blanks dropped."""
    return [line for line in text.splitlines() if line.strip()]


def render_input_line(operation: Operation, row: Mapping[str, str]) -> str:
    """One stdin line for the script: the input line format filled from a row."""
    line = operation.input_line_format or ""
    for name in operation.fields:
        line = line.replace(f"<{name}>", row.get(name, ""))
    return line


def read_input_csv(
    operation: Operation, text: str
) -> tuple[list[str], list[list[str]]]:
    """Render a header CSV into input lines, as a spreadsheet launch does.

    Every input field must be a column; other columns are ignored and rows
    with nothing in any field column are skipped. Returns the rendered lines
    and, per line, the field values (for the launch record).
    """
    fields = operation.fields
    if not fields:
        raise InputError(
            f"{operation.operation_name} reads nothing from stdin, "
            "so there is no input line format to render a CSV through"
        )
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    missing = [name for name in fields if name not in header]
    if missing:
        raise InputError(
            f"CSV is missing columns: {', '.join(missing)}; "
            f"{operation.operation_name} input lines need: {', '.join(fields)}"
        )
    lines: list[str] = []
    cells: list[list[str]] = []
    for row in reader:
        values = {name: row.get(name) or "" for name in fields}
        if not any(value.strip() for value in values.values()):
            continue
        lines.append(render_input_line(operation, values))
        cells.append([values[name] for name in fields])
    return lines, cells


def split_input_line(operation: Operation, line: str) -> list[str]:
    """Recover the field values of one rendered input line.

    The GUI renders each input row through ``input_line_format``; here the
    caller hands us the rendered line, so this inverts the format (literal
    text between placeholders becomes the separators). A line that does not
    fit the format is kept whole in the first field column so nothing is lost.
    """
    fields = operation.fields
    if not fields:
        return []
    parts = _PLACEHOLDER.split(operation.input_line_format or "")
    literals, names = parts[0::2], parts[1::2]
    pattern = "".join(
        re.escape(literals[i]) + ("(.*)" if i == len(names) - 1 else "(.*?)")
        for i in range(len(names))
    ) + re.escape(literals[-1])
    found = re.fullmatch(pattern, line)
    if found is None:
        return [line] + [""] * (len(fields) - 1)
    values: dict[str, str] = {}
    for name, value in zip(names, found.groups()):
        values.setdefault(name, value)
    return [values[name] for name in fields]


@dataclass(frozen=True)
class LaunchPlan:
    operation: Operation
    params: dict[str, str]
    input_lines: list[str]
    user: str
    button_name: str = BUTTON_NAME
    #: field values per input line when they came from a CSV; otherwise the
    #: launch record recovers them by inverting the input line format
    input_cells: list[list[str]] | None = None

    @property
    def expanded_command(self) -> str:
        return expand_command(self.operation.command_line, self.params)


@dataclass(frozen=True)
class LaunchResult:
    subprocess_invocation_id: int
    work_id: int
    queue_name: str
    spreadsheet_uploaded_id: int
    spreadsheet_file_id: int
    input_file_id: int
    command_line: str


def write_launch_csv(plan: LaunchPlan, directory: Path) -> Path:
    """The re-runnable record of the launch: fields, Operation, then args.

    Same layout the Perl popup writes, but through the ``csv`` module so a
    value containing a comma or a quote reads back correctly.
    """
    operation = plan.operation
    arg_names = sorted(plan.params)
    handle = tempfile.NamedTemporaryFile(
        "w", dir=directory, prefix="launch-", suffix=".csv", delete=False, newline=""
    )
    with handle:
        writer = csv.writer(handle)
        writer.writerow([*operation.fields, "Operation", *arg_names])
        rows = plan.input_cells
        if rows is None:
            rows = [split_input_line(operation, line) for line in plan.input_lines]
        if not rows:
            rows = [[""] * len(operation.fields)]
        for index, cells in enumerate(rows):
            if index == 0:
                cells = [*cells, operation.operation_name]
                cells += [plan.params[name] for name in arg_names]
            else:
                cells = [*cells, ""] + [""] * len(arg_names)
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


def _import_and_remove(path: Path, import_file: ImportFile, comment: str) -> int:
    try:
        return int(import_file(str(path), comment))
    finally:
        path.unlink(missing_ok=True)


def launch(
    conn: Any,
    plan: LaunchPlan,
    *,
    import_file: ImportFile,
    push_work: PushWork,
    temp_dir: Path | None = None,
) -> LaunchResult:
    """Record and queue the launch. See the module docstring for the steps.

    ``import_file(path, comment) -> file_id`` puts a local file into Posda;
    ``push_work(queue_name, work_id)`` LPUSHes on Redis. Both are injected so
    the sequence can be tested without a running stack.
    """
    directory = temp_dir or Path(tempfile.gettempdir())
    spreadsheet_file_id = _import_and_remove(
        write_launch_csv(plan, directory), import_file, LAUNCH_CSV_COMMENT
    )
    input_file_id = _import_and_remove(
        write_input_file(plan, directory), import_file, INPUT_FILE_COMMENT
    )

    queue_name = plan.operation.queue_name
    ids = _record_launch(conn, plan, spreadsheet_file_id, input_file_id, queue_name)
    spreadsheet_uploaded_id, invocation_id, work_id = ids

    try:
        push_work(queue_name, work_id)
    except Exception as exc:
        raise WorkNotQueuedError(work_id, invocation_id, queue_name) from exc

    return LaunchResult(
        subprocess_invocation_id=invocation_id,
        work_id=work_id,
        queue_name=queue_name,
        spreadsheet_uploaded_id=spreadsheet_uploaded_id,
        spreadsheet_file_id=spreadsheet_file_id,
        input_file_id=input_file_id,
        command_line=plan.expanded_command,
    )


def _record_launch(
    conn: Any,
    plan: LaunchPlan,
    spreadsheet_file_id: int,
    input_file_id: int,
    queue_name: str,
) -> tuple[int, int, int]:
    """The three inserts, in one transaction, on a connection that may be
    in autocommit mode (``posda.database`` pools them that way)."""
    was_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into spreadsheet_uploaded
                  (time_uploaded, is_executable, uploading_user,
                   file_id_in_posda, number_rows)
                values (now(), true, %s, %s, %s)
                returning spreadsheet_uploaded_id
                """,
                [plan.user, spreadsheet_file_id, len(plan.input_lines)],
            )
            spreadsheet_uploaded_id = int(cur.fetchone()[0])
            cur.execute(
                """
                insert into subprocess_invocation
                  (from_spreadsheet, from_button, query_invoked_by_dbif_id,
                   button_name, command_line, spreadsheet_uploaded_id,
                   invoking_user, when_invoked, operation_name)
                values (false, true, null, %s, %s, %s, %s, now(), %s)
                returning subprocess_invocation_id
                """,
                [
                    plan.button_name,
                    plan.expanded_command,
                    spreadsheet_uploaded_id,
                    plan.user,
                    plan.operation.operation_name,
                ],
            )
            invocation_id = int(cur.fetchone()[0])
            cur.execute(
                """
                insert into work
                  (subprocess_invocation_id, input_file_id, background_queue_name)
                values (%s, %s, %s)
                returning work_id
                """,
                [invocation_id, input_file_id, queue_name],
            )
            work_id = int(cur.fetchone()[0])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = was_autocommit
    return spreadsheet_uploaded_id, invocation_id, work_id
