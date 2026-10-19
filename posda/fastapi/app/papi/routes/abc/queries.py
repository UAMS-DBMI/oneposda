"""The saved-query catalog: recent, search, workflow groups and query detail."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...services import abc_definitions as defs
from ...services import bindings as bindings_service
from ...services import workqueue
from ...services.operations import launch
from ...services.operations.background_query import background_query_plan
from ...services.queries import catalog
from ...services.queries.runner import ordered_values
from ...services.settings import get_settings
from .deps import Conn, CurrentUser, Pools

router = APIRouter()


class QuerySummaryOut(BaseModel):
    name: str
    args: list[str]
    columns: list[str]
    schema_name: str
    tags: list[str]


class QueryListsOut(BaseModel):
    recent: list[QuerySummaryOut]
    frequent: list[QuerySummaryOut]


class ChainedQueryOut(BaseModel):
    chained_query_id: str
    caption: str
    to_query: str
    arg_map: dict[str, str]


class ProcessingButtonOut(BaseModel):
    caption: str
    operation: str


class ColumnButtonOut(BaseModel):
    button_id: str
    caption: str
    column: str
    obj: str
    col_to_param: dict[str, str]
    operation: str | None


class QueryDetailOut(QuerySummaryOut):
    description: str
    query: str
    is_select: bool
    runnable: bool
    not_runnable_reason: str | None
    chained_queries: list[ChainedQueryOut]
    processing_buttons: list[ProcessingButtonOut]
    column_buttons: list[ColumnButtonOut]


class BackgroundQueryIn(BaseModel):
    args: dict[str, str | None] = {}
    activity_id: int | None = None


class BackgroundQueryOut(BaseModel):
    subprocess_invocation_id: int
    work_id: int
    queue_name: str
    pending_work: int
    command_line: str


class WorkflowGroupEntryOut(BaseModel):
    caption: str
    query_name: str
    query: QuerySummaryOut | None


class WorkflowGroupOut(BaseModel):
    name: str
    title: str
    queries: list[WorkflowGroupEntryOut]


def _summary_out(summary: catalog.QuerySummary) -> QuerySummaryOut:
    return QuerySummaryOut(
        name=summary.name,
        args=summary.args,
        columns=summary.columns,
        schema_name=summary.schema,
        tags=summary.tags,
    )


def _detail_out(detail: catalog.QueryDetail) -> QueryDetailOut:
    return QueryDetailOut(
        name=detail.name,
        args=detail.args,
        columns=detail.columns,
        schema_name=detail.schema,
        tags=detail.tags,
        description=detail.description,
        query=detail.query,
        is_select=detail.is_select,
        runnable=detail.runnable,
        not_runnable_reason=detail.not_runnable_reason,
        chained_queries=[
            ChainedQueryOut(
                chained_query_id=c.chained_query_id,
                caption=c.caption,
                to_query=c.to_query,
                arg_map=c.arg_map,
            )
            for c in detail.chained_queries
        ],
        processing_buttons=[
            ProcessingButtonOut(caption=b.caption, operation=b.operation)
            for b in detail.processing_buttons
        ],
        column_buttons=[
            ColumnButtonOut(
                button_id=b.button_id,
                caption=b.caption,
                column=b.column,
                obj=b.obj,
                col_to_param=b.col_to_param,
                operation=b.operation,
            )
            for b in detail.column_buttons
        ],
    )


@router.get("/recent", response_model=QueryListsOut)
async def recent_queries(conn: Conn, user: CurrentUser) -> QueryListsOut:
    lists = await catalog.recent_and_frequent(conn, user.username)
    return QueryListsOut(
        recent=[_summary_out(q) for q in lists.recent],
        frequent=[_summary_out(q) for q in lists.frequent],
    )


@router.get("/search", response_model=list[QuerySummaryOut])
async def search_queries(
    conn: Conn,
    args: str | None = Query(default=None),
    columns: str | None = Query(default=None),
    sql: str | None = Query(default=None),
    name: str | None = Query(default=None),
) -> list[QuerySummaryOut]:
    found = await catalog.search(conn, args=args, columns=columns, sql=sql, name=name)
    return [_summary_out(q) for q in found]


@router.get("/workflow-groups", response_model=list[WorkflowGroupOut])
async def workflow_groups(conn: Conn) -> list[WorkflowGroupOut]:
    groups = await catalog.workflow_groups(conn)
    return [
        WorkflowGroupOut(
            name=group.name,
            title=group.title,
            queries=[
                WorkflowGroupEntryOut(
                    caption=caption,
                    query_name=query_name,
                    query=(
                        _summary_out(found[query_name]) if query_name in found else None
                    ),
                )
                for caption, query_name in group.queries
            ],
        )
        for group, found in groups
    ]


@router.get("/{name}", response_model=QueryDetailOut)
async def query_detail(name: str, conn: Conn, pools: Pools) -> QueryDetailOut:
    try:
        detail = await catalog.get_query(conn, name, pools)
    except catalog.QueryNotFound:
        raise HTTPException(status_code=404, detail=f"query {name} does not exist")
    return _detail_out(detail)


def chained_query_or_404(chained_query_id: str) -> defs.ChainedQuery:
    chain = defs.chained_query(chained_query_id)
    if chain is None:
        raise HTTPException(
            status_code=404, detail=f"no chained query {chained_query_id}"
        )
    return chain


@router.post("/{name}/background", response_model=BackgroundQueryOut, status_code=201)
async def run_in_background(
    name: str, body: BackgroundQueryIn, conn: Conn, pools: Pools, user: CurrentUser
) -> BackgroundQueryOut:
    """Queue RunQueryInBackground.pl for the query; results arrive in the inbox."""
    try:
        detail = await catalog.get_query(conn, name, pools)
    except catalog.QueryNotFound:
        raise HTTPException(status_code=404, detail=f"query {name} does not exist")
    unknown = sorted(set(body.args) - set(detail.args))
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown argument(s): {', '.join(unknown)}"
        )
    activity_id = body.activity_id
    if activity_id is None:
        bound = await bindings_service.get_binding(conn, user.username, "activity_id")
        activity_id = int(bound) if bound and bound.isdigit() else None
    values = ordered_values(detail.args, body.args)
    if detail.args:
        await bindings_service.set_bindings(
            conn, user.username, dict(zip(detail.args, values))
        )
    plan = background_query_plan(
        detail, values, activity_id=activity_id, notify=user.username
    )
    try:
        result = await launch.launch(
            conn, workqueue.get_work_queue(), get_settings(), plan, user=user.username
        )
    except launch.WorkNotQueued as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return BackgroundQueryOut(
        subprocess_invocation_id=result.subprocess_invocation_id,
        work_id=result.work_id,
        queue_name=result.queue_name,
        pending_work=result.pending_work,
        command_line=result.command_line,
    )
