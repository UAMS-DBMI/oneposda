"""Per-user variable bindings (the Perl GUI's BindingCache).

Backed by ``user_variable_binding``. The ABC UI uses these to remember the
selected activity and to pre-fill query and operation arguments with the value
the user last supplied.
"""

from collections.abc import Mapping

import asyncpg

Bindings = dict[str, str | None]

_SELECT_SQL = """
    select bound_variable_name, bound_value
    from user_variable_binding
    where binding_user = $1
    order by bound_variable_name
"""

_UPSERT_SQL = """
    insert into user_variable_binding (binding_user, bound_variable_name, bound_value)
    values ($1, $2, $3)
    on conflict (binding_user, bound_variable_name)
    do update set bound_value = excluded.bound_value
"""


async def get_bindings(conn: asyncpg.Connection, user: str) -> Bindings:
    rows = await conn.fetch(_SELECT_SQL, user)
    return {row["bound_variable_name"]: row["bound_value"] for row in rows}


async def get_binding(conn: asyncpg.Connection, user: str, name: str) -> str | None:
    return await conn.fetchval(
        "select bound_value from user_variable_binding"
        " where binding_user = $1 and bound_variable_name = $2",
        user,
        name,
    )


async def set_bindings(
    conn: asyncpg.Connection, user: str, values: Mapping[str, str | None]
) -> None:
    """Insert or replace every binding in ``values``."""
    for name in values:
        if not name:
            raise ValueError("binding names must not be empty")
    if not values:
        return
    await conn.executemany(
        _UPSERT_SQL, [(user, name, value) for name, value in values.items()]
    )
