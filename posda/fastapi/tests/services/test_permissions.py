import asyncpg

from papi.services.permissions import (
    ABC_APP,
    LAUNCH,
    has_permission,
    launchable_apps,
    load_permissions,
)

TEST_USER = "abc-test-user"


async def grant(conn: asyncpg.Connection, user: str, app: str, permission: str) -> None:
    user_id = await conn.fetchval(
        "select user_id from auth.users where user_name = $1", user
    )
    if user_id is None:
        user_id = await conn.fetchval(
            "insert into auth.users (user_name, full_name, password)"
            " values ($1, $1, 'x,y') returning user_id",
            user,
        )
    permission_id = await conn.fetchval(
        "select permission_id from auth.permissions natural join auth.apps"
        " where app_name = $1 and permission_name = $2",
        app,
        permission,
    )
    assert permission_id is not None, f"{app}/{permission} is not seeded"
    await conn.execute(
        "insert into auth.user_permissions (user_id, permission_id) values ($1, $2)",
        user_id,
        permission_id,
    )


async def test_unknown_user_has_no_permissions(conn: asyncpg.Connection) -> None:
    assert await load_permissions(conn, "no-such-user") == {}


async def test_granted_permission_is_visible(conn: asyncpg.Connection) -> None:
    await grant(conn, TEST_USER, ABC_APP, LAUNCH)

    permissions = await load_permissions(conn, TEST_USER)

    assert has_permission(permissions, ABC_APP, LAUNCH)
    assert not has_permission(permissions, ABC_APP, "debug")
    assert launchable_apps(permissions) == [ABC_APP]


def test_has_permission_on_empty_mapping() -> None:
    assert not has_permission({}, ABC_APP, LAUNCH)
    assert launchable_apps({"X": frozenset({"debug"})}) == []
