"""The ``dbif_config.spreadsheet_operation`` table."""

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from ..settings import get_settings
from .placeholders import Placeholders, parse, program_name


class OperationNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Operation:
    operation_name: str
    command_line: str
    operation_type: str | None
    input_line_format: str
    tags: list[str]
    can_chain: bool
    outdated: bool
    worker_priority: int
    placeholders: Placeholders

    @property
    def args(self) -> list[str]:
        return self.placeholders.args

    @property
    def meta_args(self) -> list[str]:
        return self.placeholders.meta_args

    @property
    def fields(self) -> list[str]:
        return self.placeholders.fields

    @property
    def needs_input(self) -> bool:
        return bool(self.input_line_format)

    @property
    def program(self) -> str | None:
        return program_name(self.command_line)


@dataclass(frozen=True)
class Candidate:
    operation: Operation
    matches: int


_COLUMNS = (
    "operation_name, command_line, operation_type, input_line_format, tags, "
    "can_chain, outdated, worker_priority"
)


def _operation(row: asyncpg.Record) -> Operation:
    command_line = row["command_line"] or ""
    input_line_format = row["input_line_format"] or ""
    return Operation(
        operation_name=row["operation_name"],
        command_line=command_line,
        operation_type=row["operation_type"],
        input_line_format=input_line_format,
        tags=list(row["tags"] or []),
        can_chain=bool(row["can_chain"]),
        outdated=bool(row["outdated"]),
        worker_priority=int(row["worker_priority"] or 0),
        placeholders=parse(command_line, input_line_format),
    )


async def list_operations(
    conn: asyncpg.Connection, *, name_like: str | None = None, tags: Sequence[str] = ()
) -> list[Operation]:
    rows = await conn.fetch(
        f"""
        select {_COLUMNS} from spreadsheet_operation
        where ($1::text is null or operation_name ilike '%' || $1 || '%')
          and ($2::text[] is null or tags && $2)
        order by operation_name
        """,
        name_like or None,
        list(tags) or None,
    )
    return [_operation(r) for r in rows]


async def get_operation(conn: asyncpg.Connection, name: str) -> Operation:
    row = await conn.fetchrow(
        f"select {_COLUMNS} from spreadsheet_operation where operation_name = $1", name
    )
    if row is None:
        raise OperationNotFound(name)
    return _operation(row)


async def operation_names(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("select operation_name from spreadsheet_operation")
    return {r["operation_name"] for r in rows}


def rank_candidates(
    operations: Sequence[Operation], columns: Sequence[str]
) -> list[Candidate]:
    """Operations whose input fields all appear in ``columns``.

    Ordered by number of matched fields, then name, like
    ``ProcessUploadedSpreadsheetWithNoOperation``. Operations without an
    input line format never qualify.
    """
    present = set(columns)
    candidates = [
        Candidate(op, len(op.fields))
        for op in operations
        if op.needs_input and op.fields and set(op.fields) <= present
    ]
    return sorted(candidates, key=lambda c: (-c.matches, c.operation.operation_name))


async def candidate_operations(
    conn: asyncpg.Connection, columns: Sequence[str]
) -> list[Candidate]:
    return rank_candidates(await list_operations(conn), columns)


def script_dirs() -> list[Path]:
    """Where operation scripts live: PATH plus the posdatools bin directories."""
    settings = get_settings()
    dirs = [Path(p) for p in (shutil.os.environ.get("PATH") or "").split(":") if p]
    dirs.extend(sorted(settings.posdatools_root.glob("*/bin")))
    return dirs


def program_found(operation: Operation) -> bool | None:
    """Whether the command's program exists; None when it cannot be checked."""
    program = operation.program
    if not program:
        return None
    if "/" in program:
        return Path(program).exists()
    for directory in script_dirs():
        if (directory / program).is_file():
            return True
    return False
