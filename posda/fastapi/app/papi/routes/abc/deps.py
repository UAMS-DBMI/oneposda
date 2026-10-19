"""Request dependencies shared by the ABC routers."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import asyncpg
from fastapi import Depends, HTTPException
from starlette.status import HTTP_403_FORBIDDEN

from ...services.db_pools import PoolRegistry, get_pools
from ...services.permissions import (
    ABC_APP,
    LAUNCH,
    Permissions,
    has_permission,
    load_permissions,
)
from ...util import db as database
from ..auth import User, get_current_active_user


@dataclass(frozen=True)
class AbcUser:
    username: str
    full_name: str | None
    permissions: Permissions

    def can(self, app: str, permission: str) -> bool:
        return has_permission(self.permissions, app, permission)


async def acquire_connection() -> AsyncIterator[asyncpg.Connection]:
    """One pooled connection for the whole request."""
    async with database.pool.acquire() as conn:
        yield conn


async def current_abc_user(
    user: User = Depends(get_current_active_user),
    conn: asyncpg.Connection = Depends(acquire_connection),
) -> AbcUser:
    permissions = await load_permissions(conn, user.username)
    if not has_permission(permissions, ABC_APP, LAUNCH):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"{user.username} may not launch {ABC_APP}",
        )
    return AbcUser(
        username=user.username, full_name=user.full_name, permissions=permissions
    )


Conn = Annotated[asyncpg.Connection, Depends(acquire_connection)]
CurrentUser = Annotated[AbcUser, Depends(current_abc_user)]
Pools = Annotated[PoolRegistry, Depends(get_pools)]
