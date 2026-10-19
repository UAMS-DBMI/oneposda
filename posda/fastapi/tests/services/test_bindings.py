import asyncpg
import pytest

from papi.services.bindings import get_binding, get_bindings, set_bindings

USER = "abc-bindings-test"


async def test_round_trip_and_overwrite(conn: asyncpg.Connection) -> None:
    await set_bindings(conn, USER, {"activity_id": "12", "notify": "someone"})
    assert await get_bindings(conn, USER) == {"activity_id": "12", "notify": "someone"}

    await set_bindings(conn, USER, {"activity_id": "13"})

    assert await get_binding(conn, USER, "activity_id") == "13"
    assert await get_binding(conn, USER, "notify") == "someone"
    count = await conn.fetchval(
        "select count(*) from user_variable_binding where binding_user = $1", USER
    )
    assert count == 2


async def test_null_value_is_stored(conn: asyncpg.Connection) -> None:
    await set_bindings(conn, USER, {"activity_id": None})
    assert await get_bindings(conn, USER) == {"activity_id": None}


async def test_missing_binding_is_none(conn: asyncpg.Connection) -> None:
    assert await get_binding(conn, USER, "never-set") is None


async def test_empty_name_rejected(conn: asyncpg.Connection) -> None:
    with pytest.raises(ValueError):
        await set_bindings(conn, USER, {"": "x"})
