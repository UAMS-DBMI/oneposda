"""The signed-in user and their variable bindings."""

from fastapi import APIRouter, Response
from pydantic import BaseModel

from ...services import bindings
from ...services.permissions import launchable_apps
from .deps import Conn, CurrentUser

router = APIRouter()


class MeResponse(BaseModel):
    username: str
    full_name: str | None
    permissions: dict[str, list[str]]
    launchable_apps: list[str]


class BindingValue(BaseModel):
    value: str | None


@router.get("", response_model=MeResponse)
async def read_me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        username=user.username,
        full_name=user.full_name,
        permissions={app: sorted(names) for app, names in user.permissions.items()},
        launchable_apps=launchable_apps(user.permissions),
    )


@router.get("/bindings")
async def read_bindings(conn: Conn, user: CurrentUser) -> dict[str, str | None]:
    return await bindings.get_bindings(conn, user.username)


@router.put("/bindings", status_code=204)
async def write_bindings(
    values: dict[str, str | None], conn: Conn, user: CurrentUser
) -> Response:
    await bindings.set_bindings(conn, user.username, values)
    return Response(status_code=204)


@router.put("/bindings/{name}", status_code=204)
async def write_binding(
    name: str, body: BindingValue, conn: Conn, user: CurrentUser
) -> Response:
    await bindings.set_bindings(conn, user.username, {name: body.value})
    return Response(status_code=204)
