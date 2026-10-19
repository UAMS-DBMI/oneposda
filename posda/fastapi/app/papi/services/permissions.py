"""Per-user application permissions (port of Posda::Permissions)."""

import asyncpg

Permissions = dict[str, frozenset[str]]

ABC_APP = "ActivityBasedCuration"
USER_ADMIN_APP = "UserAdmin"
LAUNCH = "launch"

_PERMISSIONS_SQL = """
    select app_name, permission_name
    from auth.user_permissions
    natural join auth.users
    natural join auth.apps
    natural join auth.permissions
    where user_name = $1
"""


async def load_permissions(conn: asyncpg.Connection, username: str) -> Permissions:
    rows = await conn.fetch(_PERMISSIONS_SQL, username)
    grouped: dict[str, set[str]] = {}
    for row in rows:
        grouped.setdefault(row["app_name"], set()).add(row["permission_name"])
    return {app: frozenset(names) for app, names in grouped.items()}


def has_permission(permissions: Permissions, app: str, permission: str) -> bool:
    return permission in permissions.get(app, frozenset())


def launchable_apps(permissions: Permissions) -> list[str]:
    return sorted(app for app, names in permissions.items() if LAUNCH in names)
