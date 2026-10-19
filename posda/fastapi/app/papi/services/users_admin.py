"""User administration (the UserAdmin app): accounts, passwords, permissions.

Accounts are ``auth.users``; a matching ``user_inbox`` row carries the
email address and is what lets background reports reach the user, so the
two are created and removed together, as the Perl app did.
"""

from dataclasses import dataclass

import asyncpg

from ..util import password as passwords

Permissions = dict[str, dict[str, bool]]  # app -> permission -> granted


class UserNotFound(LookupError):
    pass


class UserExists(ValueError):
    pass


class BadPermission(ValueError):
    pass


class UserInUse(RuntimeError):
    """The account is referenced by other records and cannot be deleted."""


@dataclass(frozen=True)
class UserAccount:
    user_id: int
    user_name: str
    full_name: str
    disabled: bool
    email: str | None


def normalise_username(name: str) -> str:
    cleaned = name.strip().lower()  # usernames were always forced to lowercase
    if not cleaned or any(c.isspace() for c in cleaned):
        raise ValueError("user name must be a single non-blank word")
    return cleaned


async def list_users(conn: asyncpg.Connection) -> list[UserAccount]:
    rows = await conn.fetch("""
        select u.user_id, u.user_name, u.full_name, u.disabled, i.user_email_addr as email
        from auth.users u
        left join user_inbox i on i.user_name = u.user_name
        order by u.user_name
        """)
    return [UserAccount(**dict(r)) for r in rows]


async def get_user(conn: asyncpg.Connection, user_name: str) -> UserAccount:
    row = await conn.fetchrow(
        """
        select u.user_id, u.user_name, u.full_name, u.disabled, i.user_email_addr as email
        from auth.users u
        left join user_inbox i on i.user_name = u.user_name
        where u.user_name = $1
        """,
        user_name,
    )
    if row is None:
        raise UserNotFound(user_name)
    return UserAccount(**dict(row))


async def all_permissions(conn: asyncpg.Connection) -> Permissions:
    """Every app and permission, all unset."""
    rows = await conn.fetch(
        "select a.app_name, p.permission_name from auth.permissions p "
        "join auth.apps a using (app_id) order by a.app_name, p.permission_name"
    )
    result: Permissions = {}
    for row in rows:
        result.setdefault(row["app_name"], {})[row["permission_name"]] = False
    return result


async def user_permissions(conn: asyncpg.Connection, user_name: str) -> Permissions:
    result = await all_permissions(conn)
    rows = await conn.fetch(
        """
        select a.app_name, p.permission_name
        from auth.user_permissions up
        join auth.users u using (user_id)
        join auth.permissions p using (permission_id)
        join auth.apps a on a.app_id = p.app_id
        where u.user_name = $1
        """,
        user_name,
    )
    for row in rows:
        result.setdefault(row["app_name"], {})[row["permission_name"]] = True
    return result


async def set_permissions(
    conn: asyncpg.Connection, user_name: str, granted: dict[str, list[str]]
) -> None:
    """Replace the user's permissions with exactly ``granted`` (app -> names)."""
    user = await get_user(conn, user_name)
    known = await all_permissions(conn)
    for app, names in granted.items():
        for name in names:
            if name not in known.get(app, {}):
                raise BadPermission(f"{app}/{name}")
    async with conn.transaction():
        await conn.execute(
            "delete from auth.user_permissions where user_id = $1", user.user_id
        )
        await conn.executemany(
            """
            insert into auth.user_permissions (user_id, permission_id)
            select $1, p.permission_id
            from auth.permissions p join auth.apps a using (app_id)
            where a.app_name = $2 and p.permission_name = $3
            """,
            [
                (user.user_id, app, name)
                for app, names in granted.items()
                for name in names
            ],
        )


async def create_user(
    conn: asyncpg.Connection,
    user_name: str,
    *,
    full_name: str,
    email: str | None,
    password: str,
) -> UserAccount:
    name = normalise_username(user_name)
    if not password:
        raise ValueError("a password is required")
    async with conn.transaction():
        try:
            await conn.execute(
                "insert into auth.users (user_name, full_name, password) values ($1, $2, $3)",
                name,
                full_name.strip(),
                passwords.encode(password),
            )
        except asyncpg.UniqueViolationError:
            raise UserExists(name) from None
        await conn.execute(
            "insert into user_inbox (user_name, user_email_addr) values ($1, $2) "
            "on conflict (user_name) do update set user_email_addr = excluded.user_email_addr",
            name,
            email,
        )
    return await get_user(conn, name)


async def set_password(conn: asyncpg.Connection, user_name: str, password: str) -> None:
    if not password:
        raise ValueError("a password is required")
    status = await conn.execute(
        "update auth.users set password = $2 where user_name = $1",
        user_name,
        passwords.encode(password),
    )
    if status.endswith(" 0"):
        raise UserNotFound(user_name)


async def update_user(
    conn: asyncpg.Connection,
    user_name: str,
    *,
    full_name: str | None = None,
    email: str | None = None,
    disabled: bool | None = None,
) -> UserAccount:
    await get_user(conn, user_name)
    async with conn.transaction():
        if full_name is not None:
            await conn.execute(
                "update auth.users set full_name = $2 where user_name = $1",
                user_name,
                full_name.strip(),
            )
        if disabled is not None:
            await conn.execute(
                "update auth.users set disabled = $2 where user_name = $1",
                user_name,
                disabled,
            )
        if email is not None:
            await conn.execute(
                "insert into user_inbox (user_name, user_email_addr) values ($1, $2) "
                "on conflict (user_name) do update set user_email_addr = excluded.user_email_addr",
                user_name,
                email,
            )
    return await get_user(conn, user_name)


async def delete_user(conn: asyncpg.Connection, user_name: str) -> None:
    user = await get_user(conn, user_name)
    async with conn.transaction():
        try:
            await conn.execute(
                "delete from auth.users where user_id = $1", user.user_id
            )
        except asyncpg.ForeignKeyViolationError as exc:
            raise UserInUse(
                f"{user_name} is referenced by other records; disable the account instead"
            ) from exc
        await conn.execute("delete from user_inbox where user_name = $1", user_name)
