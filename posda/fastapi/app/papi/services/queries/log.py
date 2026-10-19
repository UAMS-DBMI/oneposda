"""The query log the Perl GUI wrote through Posda::QueryLog.

``query_invoked_by_dbif`` and ``dbif_query_args`` feed the "recent" and
"frequent" query lists, and ``subprocess_invocation.query_invoked_by_dbif_id``
ties an operation launched from a result back to the query that produced it.
"""

from collections.abc import Sequence
from datetime import datetime

import asyncpg


async def query_invoked(
    conn: asyncpg.Connection,
    query_name: str,
    arg_names: Sequence[str],
    arg_values: Sequence[str | None],
    user: str,
    *,
    started_at: datetime | None = None,
) -> int:
    """Record the start of a run and its arguments; returns the log id."""
    invoked_id = await conn.fetchval(
        """
        insert into query_invoked_by_dbif
          (query_name, invoking_user, query_start_time)
        values ($1, $2, coalesce($3, now()))
        returning query_invoked_by_dbif_id
        """,
        query_name,
        user,
        started_at,
    )
    await conn.executemany(
        "insert into dbif_query_args values ($1, $2, $3, $4)",
        [
            (invoked_id, index, name, value)
            for index, (name, value) in enumerate(zip(arg_names, arg_values))
        ],
    )
    return int(invoked_id)


async def query_finished(
    conn: asyncpg.Connection, invoked_id: int, row_count: int
) -> None:
    await conn.execute(
        """
        update query_invoked_by_dbif
        set query_end_time = now(), number_of_rows = $2
        where query_invoked_by_dbif_id = $1
        """,
        invoked_id,
        row_count,
    )
