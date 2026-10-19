import pytest

from papi.services import users_admin
from papi.util.password import is_valid

NAME = "admin-test-user"


async def test_create_update_permissions_password_delete(conn) -> None:
    created = await users_admin.create_user(
        conn,
        " Admin-Test-User ",
        full_name="Test Person",
        email="t@example.invalid",
        password="pw1",
    )
    assert created.user_name == NAME
    assert created.email == "t@example.invalid"
    assert created.disabled is False
    assert NAME in [u.user_name for u in await users_admin.list_users(conn)]

    with pytest.raises(users_admin.UserExists):
        await users_admin.create_user(
            conn, NAME, full_name="", email=None, password="x"
        )

    perms = await users_admin.user_permissions(conn, NAME)
    assert perms["ActivityBasedCuration"] == {"debug": False, "launch": False}
    await users_admin.set_permissions(
        conn,
        NAME,
        {"ActivityBasedCuration": ["launch"], "UserAdmin": ["launch", "debug"]},
    )
    perms = await users_admin.user_permissions(conn, NAME)
    assert perms["ActivityBasedCuration"]["launch"] is True
    assert perms["ActivityBasedCuration"]["debug"] is False
    assert perms["UserAdmin"] == {"debug": True, "launch": True}
    await users_admin.set_permissions(conn, NAME, {})
    assert not any(
        any(v.values())
        for v in (await users_admin.user_permissions(conn, NAME)).values()
    )
    with pytest.raises(users_admin.BadPermission):
        await users_admin.set_permissions(
            conn, NAME, {"ActivityBasedCuration": ["fly"]}
        )

    await users_admin.set_password(conn, NAME, "pw2")
    stored = await conn.fetchval(
        "select password from auth.users where user_name = $1", NAME
    )
    assert is_valid(stored, "pw2") and not is_valid(stored, "pw1")

    updated = await users_admin.update_user(
        conn, NAME, disabled=True, email="new@example.invalid"
    )
    assert updated.disabled is True and updated.email == "new@example.invalid"

    await users_admin.delete_user(conn, NAME)
    with pytest.raises(users_admin.UserNotFound):
        await users_admin.get_user(conn, NAME)
    assert (
        await conn.fetchval(
            "select count(*) from user_inbox where user_name = $1", NAME
        )
        == 0
    )


def test_normalise_username() -> None:
    assert users_admin.normalise_username(" Bob ") == "bob"
    with pytest.raises(ValueError):
        users_admin.normalise_username("two words")
    with pytest.raises(ValueError):
        users_admin.normalise_username("  ")
