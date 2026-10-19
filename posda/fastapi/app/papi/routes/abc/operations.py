"""Operations: catalog, candidates for a set of columns, prepare and launch.

``prepare`` returns the editable preview the Perl popup showed (resolved
args with their sources, the expanded command, the input lines); ``launch``
re-derives the rows server-side from the same source description, so the
client never uploads row data back.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...services import bindings as bindings_service
from ...services import workqueue
from ...services.files import file_path
from ...services.operations import catalog, launch, resolve, spreadsheets
from ...services.queries import runner
from ...services.settings import get_settings
from .deps import Conn, CurrentUser

router = APIRouter()

PREVIEW_HEAD = 10
PREVIEW_TAIL = 10


# --- models ---------------------------------------------------------------


class OperationOut(BaseModel):
    operation_name: str
    command_line: str
    operation_type: str | None
    input_line_format: str
    tags: list[str]
    can_chain: bool
    outdated: bool
    worker_priority: int
    args: list[str]
    meta_args: list[str]
    fields: list[str]
    program: str | None
    program_found: bool | None


class CandidateOut(BaseModel):
    operation: OperationOut
    matches: int


class CandidatesOut(BaseModel):
    columns: list[str]
    row_count: int
    named_operation: str | None
    candidates: list[CandidateOut]


class WorkflowSource(BaseModel):
    type: Literal["workflow"]
    operation: str
    caption: str | None = None
    prior_args: dict[str, str] = {}


class TableSource(BaseModel):
    type: Literal["table"]
    query_run_id: int
    filtered: bool = False
    operation: str
    caption: str | None = None


class RowSource(BaseModel):
    type: Literal["row"]
    query_run_id: int
    filtered: bool = False
    row_index: int
    operation: str
    caption: str | None = None


class CompareTimepointsSource(BaseModel):
    type: Literal["compare_timepoints"]
    activity_id: int
    from_timepoint_id: int
    to_timepoint_id: int


class SpreadsheetSource(BaseModel):
    type: Literal["spreadsheet"]
    file_id: int
    operation: str | None = None  # required when the sheet has no Operation column


Source = Annotated[
    WorkflowSource
    | TableSource
    | RowSource
    | CompareTimepointsSource
    | SpreadsheetSource,
    Field(discriminator="type"),
]


class PrepareIn(BaseModel):
    source: Source


class ResolvedArgOut(BaseModel):
    value: str
    source: str


class PreviewOut(BaseModel):
    operation: OperationOut
    button_name: str
    args: dict[str, ResolvedArgOut]
    expanded_command: str
    input_line_count: int
    input_head: list[str]
    input_tail: list[str]
    spreadsheet_file_id: int | None
    query_invoked_by_dbif_id: int | None


class LaunchIn(BaseModel):
    source: Source
    args: dict[str, str]


class LaunchOut(BaseModel):
    subprocess_invocation_id: int
    work_id: int
    queue_name: str
    pending_work: int
    command_line: str


# --- helpers --------------------------------------------------------------


def _operation_out(op: catalog.Operation) -> OperationOut:
    return OperationOut(
        operation_name=op.operation_name,
        command_line=op.command_line,
        operation_type=op.operation_type,
        input_line_format=op.input_line_format,
        tags=op.tags,
        can_chain=op.can_chain,
        outdated=op.outdated,
        worker_priority=op.worker_priority,
        args=op.args,
        meta_args=op.meta_args,
        fields=op.fields,
        program=op.program,
        program_found=catalog.program_found(op),
    )


async def _operation_or_404(conn: Conn, name: str) -> catalog.Operation:
    try:
        return await catalog.get_operation(conn, name)
    except catalog.OperationNotFound:
        raise HTTPException(status_code=404, detail=f"operation {name} does not exist")


async def _run_rows(conn: Conn, user: CurrentUser, run_id: int, filtered: bool):
    """All rows of a run as dicts, plus its columns and log id."""
    try:
        run = await runner.load_users_run(conn, run_id, user.username)
    except runner.RunNotFound:
        raise HTTPException(status_code=404, detail=f"query run {run_id} not found")
    columns = runner.read_columns(run.spool_dir)
    page, total = await runner.page(
        run, 0, max(run.row_count, 1), filtered=filtered and bool(run.filter)
    )
    rows = [dict(zip(columns, row)) for row in page.rows]
    return run, columns, rows


async def _sheet_for(conn: Conn, file_id: int) -> spreadsheets.Sheet:
    import asyncio

    try:
        path = await file_path(conn, file_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        return await asyncio.to_thread(spreadsheets.read_sheet, path)
    except spreadsheets.SpreadsheetError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class Prepared(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    operation: catalog.Operation
    rows: list[dict]
    prior_args: dict[str, object]
    extras: dict[str, object]
    button_name: str
    spreadsheet_file_id: int | None
    query_invoked_by_dbif_id: int | None


async def _gather(conn: Conn, user: CurrentUser, source) -> Prepared:
    """Resolve a launch source to the operation, rows and seed arguments."""
    if source.type == "workflow":
        operation = await _operation_or_404(conn, source.operation)
        return Prepared(
            operation=operation,
            rows=[],
            prior_args=dict(source.prior_args),
            extras={},
            button_name=source.caption or source.operation,
            spreadsheet_file_id=None,
            query_invoked_by_dbif_id=None,
        )
    if source.type == "table":
        operation = await _operation_or_404(conn, source.operation)
        run, _, rows = await _run_rows(conn, user, source.query_run_id, source.filtered)
        return Prepared(
            operation=operation,
            rows=rows,
            prior_args={},
            extras={},
            button_name=source.caption or source.operation,
            spreadsheet_file_id=None,
            query_invoked_by_dbif_id=run.query_invoked_by_dbif_id,
        )
    if source.type == "row":
        operation = await _operation_or_404(conn, source.operation)
        run, _, rows = await _run_rows(conn, user, source.query_run_id, source.filtered)
        if not 0 <= source.row_index < len(rows):
            raise HTTPException(status_code=400, detail="row_index is out of range")
        return Prepared(
            operation=operation,
            rows=[],
            prior_args=dict(rows[source.row_index]),
            extras={},
            button_name=source.caption or source.operation,
            spreadsheet_file_id=None,
            query_invoked_by_dbif_id=run.query_invoked_by_dbif_id,
        )
    if source.type == "compare_timepoints":
        operation = await _operation_or_404(conn, "CompareTimepoints")
        extras = {
            "button": "CompareTimepoints",
            "from_timepoint_id": source.from_timepoint_id,
            "to_timepoint_id": source.to_timepoint_id,
            "activity_id": source.activity_id,
        }
        return Prepared(
            operation=operation,
            rows=[],
            prior_args={},
            extras=extras,
            button_name="CompareTimepoints",
            spreadsheet_file_id=None,
            query_invoked_by_dbif_id=None,
        )
    sheet = await _sheet_for(conn, source.file_id)
    name = source.operation or sheet.named_operation
    if name is None:
        raise HTTPException(
            status_code=400,
            detail="the spreadsheet names no Operation; choose one from the candidates",
        )
    operation = await _operation_or_404(conn, name)
    prior = {
        a: sheet.rows[0][a]
        for a in operation.args
        if sheet.rows and sheet.rows[0].get(a)
    }
    return Prepared(
        operation=operation,
        rows=sheet.rows,
        prior_args=prior,
        extras={},
        button_name=name,
        spreadsheet_file_id=source.file_id,
        query_invoked_by_dbif_id=None,
    )


async def _activity_id(conn: Conn, user: CurrentUser) -> int | None:
    raw = await bindings_service.get_binding(conn, user.username, "activity_id")
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


async def _resolved(
    conn: Conn, user: CurrentUser, prepared: Prepared
) -> dict[str, resolve.ResolvedArg]:
    activity_id = prepared.extras.get("activity_id") or await _activity_id(conn, user)
    settings = await resolve.current_settings(
        conn, user=user.username, activity_id=activity_id, extras=prepared.extras
    )
    user_bindings = await bindings_service.get_bindings(conn, user.username)
    return resolve.resolve_args(
        prepared.operation.args,
        prior_ss_args=prepared.prior_args,
        current_settings=settings,
        bindings=user_bindings,
    )


# --- routes ---------------------------------------------------------------


@router.get("", response_model=list[OperationOut])
async def list_operations(
    conn: Conn,
    q: str | None = Query(default=None),
    tags: list[str] | None = Query(default=None),
) -> list[OperationOut]:
    found = await catalog.list_operations(conn, name_like=q, tags=tags or ())
    return [_operation_out(op) for op in found]


@router.get("/candidates", response_model=CandidatesOut)
async def candidates(
    conn: Conn,
    user: CurrentUser,
    query_run_id: int | None = Query(default=None),
    filtered: bool = Query(default=False),
    file_id: int | None = Query(default=None),
) -> CandidatesOut:
    named = None
    if query_run_id is not None:
        _, columns, rows = await _run_rows(conn, user, query_run_id, filtered)
    elif file_id is not None:
        sheet = await _sheet_for(conn, file_id)
        columns, rows, named = sheet.columns, sheet.rows, sheet.named_operation
    else:
        raise HTTPException(status_code=400, detail="give query_run_id or file_id")
    ranked = await catalog.candidate_operations(conn, columns)
    return CandidatesOut(
        columns=columns,
        row_count=len(rows),
        named_operation=named,
        candidates=[
            CandidateOut(operation=_operation_out(c.operation), matches=c.matches)
            for c in ranked
        ],
    )


@router.get("/{name}", response_model=OperationOut)
async def operation_detail(name: str, conn: Conn) -> OperationOut:
    return _operation_out(await _operation_or_404(conn, name))


@router.post("/prepare", response_model=PreviewOut)
async def prepare(body: PrepareIn, conn: Conn, user: CurrentUser) -> PreviewOut:
    prepared = await _gather(conn, user, body.source)
    resolved = await _resolved(conn, user, prepared)
    plan = launch.make_plan(
        prepared.operation,
        {name: arg.value for name, arg in resolved.items()},
        prepared.rows,
        button_name=prepared.button_name,
        spreadsheet_file_id=prepared.spreadsheet_file_id,
        query_invoked_by_dbif_id=prepared.query_invoked_by_dbif_id,
    )
    lines = plan.input_lines
    return PreviewOut(
        operation=_operation_out(prepared.operation),
        button_name=prepared.button_name,
        args={
            n: ResolvedArgOut(value=a.value, source=a.source)
            for n, a in resolved.items()
        },
        expanded_command=plan.expanded_command,
        input_line_count=len(lines),
        input_head=(
            lines[:PREVIEW_HEAD] if len(lines) > PREVIEW_HEAD + PREVIEW_TAIL else lines
        ),
        input_tail=(
            lines[-PREVIEW_TAIL:] if len(lines) > PREVIEW_HEAD + PREVIEW_TAIL else []
        ),
        spreadsheet_file_id=prepared.spreadsheet_file_id,
        query_invoked_by_dbif_id=prepared.query_invoked_by_dbif_id,
    )


@router.post("/launch", response_model=LaunchOut, status_code=201)
async def launch_operation(body: LaunchIn, conn: Conn, user: CurrentUser) -> LaunchOut:
    prepared = await _gather(conn, user, body.source)
    unknown = sorted(set(body.args) - set(prepared.operation.args))
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown argument(s): {', '.join(unknown)}"
        )
    plan = launch.make_plan(
        prepared.operation,
        body.args,
        prepared.rows,
        button_name=prepared.button_name,
        spreadsheet_file_id=prepared.spreadsheet_file_id,
        query_invoked_by_dbif_id=prepared.query_invoked_by_dbif_id,
    )
    if plan.args:
        await bindings_service.set_bindings(conn, user.username, dict(plan.args))
    try:
        result = await launch.launch(
            conn, workqueue.get_work_queue(), get_settings(), plan, user=user.username
        )
    except launch.WorkNotQueued as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return LaunchOut(
        subprocess_invocation_id=result.subprocess_invocation_id,
        work_id=result.work_id,
        queue_name=result.queue_name,
        pending_work=result.pending_work,
        command_line=result.command_line,
    )
