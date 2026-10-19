"""Browsing the saved queries in ``dbif_config.queries``.

Recent/frequent lists and search reproduce what the Perl "Queries" page
showed, with the search run as a parameterised statement instead of SQL
pasted together from the form fields.
"""

from dataclasses import dataclass, field

import asyncpg

from .. import abc_definitions as defs
from ..db_pools import PoolRegistry
from .params import is_select

RECENT_LIMIT = 6
FREQUENT_LIMIT = 20


@dataclass(frozen=True)
class QuerySummary:
    name: str
    args: list[str]
    columns: list[str]
    schema: str
    tags: list[str]


@dataclass(frozen=True)
class QueryDetail:
    name: str
    args: list[str]
    columns: list[str]
    schema: str
    tags: list[str]
    description: str
    query: str
    is_select: bool
    runnable: bool
    not_runnable_reason: str | None
    chained_queries: list[defs.ChainedQuery] = field(default_factory=list)
    processing_buttons: list[defs.ProcessingButton] = field(default_factory=list)
    column_buttons: list[defs.ColumnButton] = field(default_factory=list)


@dataclass(frozen=True)
class QueryLists:
    recent: list[QuerySummary]
    frequent: list[QuerySummary]


class QueryNotFound(LookupError):
    pass


_SUMMARY_COLUMNS = "name, args, columns, schema, tags"


def _summary(row: asyncpg.Record) -> QuerySummary:
    return QuerySummary(
        name=row["name"],
        args=list(row["args"] or []),
        columns=list(row["columns"] or []),
        schema=row["schema"] or "",
        tags=list(row["tags"] or []),
    )


async def summaries_by_name(
    conn: asyncpg.Connection, names: list[str]
) -> dict[str, QuerySummary]:
    rows = await conn.fetch(
        f"select {_SUMMARY_COLUMNS} from queries where name = any($1)", names
    )
    return {row["name"]: _summary(row) for row in rows}


async def recent_and_frequent(conn: asyncpg.Connection, user: str) -> QueryLists:
    """The six most recent and twenty most used selects this user has run.

    Port of ``DrawQueryListRecent`` over
    ``ListOfQueriesPerformedByUserWithLatestAndCount``: only selects are
    listed, and the frequent list excludes anything already in the recent one.
    """
    rows = await conn.fetch(
        """
        select query_name, query,
               max(query_start_time) as last_invocation,
               count(query_invoked_by_dbif_id) as num_invocations
        from query_invoked_by_dbif i join queries q on i.query_name = q.name
        where invoking_user = $1
        group by query_name, query
        order by last_invocation desc
        """,
        user,
    )
    selects = [r for r in rows if is_select(r["query"])]
    recent_names = [r["query_name"] for r in selects[:RECENT_LIMIT]]
    by_count = sorted(selects, key=lambda r: r["num_invocations"], reverse=True)
    frequent_names: list[str] = []
    for row in by_count:
        if row["query_name"] in recent_names or row["query_name"] in frequent_names:
            continue
        frequent_names.append(row["query_name"])
        if len(frequent_names) >= FREQUENT_LIMIT:
            break
    summaries = await summaries_by_name(conn, recent_names + frequent_names)
    return QueryLists(
        recent=[summaries[n] for n in recent_names if n in summaries],
        frequent=[summaries[n] for n in frequent_names if n in summaries],
    )


def _csv_terms(text: str | None) -> list[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


async def search(
    conn: asyncpg.Connection,
    *,
    args: str | None = None,
    columns: str | None = None,
    sql: str | None = None,
    name: str | None = None,
) -> list[QuerySummary]:
    """Queries matching every comma-separated term in every given field.

    Same semantics as the Perl form: an arg or column term must equal an
    element of the array, a query or name term must appear as a substring.
    """
    clauses: list[str] = []
    params: list[str] = []

    def add(clause: str, value: str) -> None:
        params.append(value)
        clauses.append(clause.replace("?", f"${len(params)}"))

    for term in _csv_terms(args):
        add("? = any(args)", term)
    for term in _csv_terms(columns):
        add("? = any(columns)", term)
    for term in _csv_terms(sql):
        add("query like '%' || ? || '%'", term)
    for term in _csv_terms(name):
        add("name like '%' || ? || '%'", term)
    if not clauses:
        return []
    rows = await conn.fetch(
        f"select {_SUMMARY_COLUMNS} from queries where {' and '.join(clauses)} "
        "order by name",
        *params,
    )
    return [_summary(r) for r in rows]


async def get_query(
    conn: asyncpg.Connection, name: str, pools: PoolRegistry
) -> QueryDetail:
    row = await conn.fetchrow(
        "select name, args, columns, schema, tags, description, query "
        "from queries where name = $1",
        name,
    )
    if row is None:
        raise QueryNotFound(name)
    schema = row["schema"] or ""
    reason = pools.unavailable_reason(schema)
    return QueryDetail(
        name=row["name"],
        args=list(row["args"] or []),
        columns=list(row["columns"] or []),
        schema=schema,
        tags=list(row["tags"] or []),
        description=row["description"] or "",
        query=row["query"] or "",
        is_select=is_select(row["query"] or ""),
        runnable=reason is None,
        not_runnable_reason=reason,
        chained_queries=defs.chained_from(name),
        processing_buttons=defs.processing_buttons_for(name),
        column_buttons=defs.column_buttons_for(name),
    )


async def workflow_groups(
    conn: asyncpg.Connection,
) -> list[tuple[defs.WorkflowGroup, dict[str, QuerySummary]]]:
    """Each workflow group with the summaries of the queries it lists."""
    groups = defs.workflow_groups()
    names = sorted({q for g in groups for _, q in g.queries})
    summaries = await summaries_by_name(conn, names)
    return [
        (g, {q: summaries[q] for _, q in g.queries if q in summaries}) for g in groups
    ]
