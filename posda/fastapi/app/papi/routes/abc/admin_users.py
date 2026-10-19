"""User administration, for users who may launch the UserAdmin app."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...services import users_admin
from ...services.permissions import USER_ADMIN_APP
from .deps import Conn, CurrentUser, require_app

router = APIRouter(dependencies=[Depends(require_app(USER_ADMIN_APP))])


class UserOut(BaseModel):
    user_id: int
    user_name: str
    full_name: str
    disabled: bool
    email: str | None


class NewUser(BaseModel):
    user_name: str
    full_name: str = ""
    email: str | None = None
    password: str


class UserPatch(BaseModel):
    full_name: str | None = None
    email: str | None = None
    disabled: bool | None = None
    password: str | None = None


class PermissionsIn(BaseModel):
    granted: dict[str, list[str]]


def _out(user: users_admin.UserAccount) -> UserOut:
    return UserOut(**user.__dict__)


@router.get("/users", response_model=list[UserOut])
async def list_users(conn: Conn) -> list[UserOut]:
    return [_out(u) for u in await users_admin.list_users(conn)]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(body: NewUser, conn: Conn) -> UserOut:
    try:
        created = await users_admin.create_user(
            conn,
            body.user_name,
            full_name=body.full_name,
            email=body.email,
            password=body.password,
        )
    except users_admin.UserExists as exc:
        raise HTTPException(status_code=409, detail=f"user {exc} already exists")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _out(created)


@router.get("/users/{user_name}", response_model=UserOut)
async def get_user(user_name: str, conn: Conn) -> UserOut:
    try:
        return _out(await users_admin.get_user(conn, user_name))
    except users_admin.UserNotFound:
        raise HTTPException(status_code=404, detail=f"no user {user_name}")


@router.patch("/users/{user_name}", response_model=UserOut)
async def patch_user(
    user_name: str, body: UserPatch, conn: Conn, user: CurrentUser
) -> UserOut:
    if body.disabled and user_name == user.username:
        raise HTTPException(
            status_code=400, detail="you cannot disable your own account"
        )
    try:
        if body.password is not None:
            await users_admin.set_password(conn, user_name, body.password)
        updated = await users_admin.update_user(
            conn,
            user_name,
            full_name=body.full_name,
            email=body.email,
            disabled=body.disabled,
        )
    except users_admin.UserNotFound:
        raise HTTPException(status_code=404, detail=f"no user {user_name}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _out(updated)


@router.delete("/users/{user_name}", status_code=204)
async def delete_user(user_name: str, conn: Conn, user: CurrentUser) -> None:
    if user_name == user.username:
        raise HTTPException(
            status_code=400, detail="you cannot delete your own account"
        )
    try:
        await users_admin.delete_user(conn, user_name)
    except users_admin.UserNotFound:
        raise HTTPException(status_code=404, detail=f"no user {user_name}")
    except users_admin.UserInUse as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/permissions", response_model=dict[str, dict[str, bool]])
async def all_permissions(conn: Conn) -> dict[str, dict[str, bool]]:
    return await users_admin.all_permissions(conn)


@router.get("/users/{user_name}/permissions", response_model=dict[str, dict[str, bool]])
async def get_permissions(user_name: str, conn: Conn) -> dict[str, dict[str, bool]]:
    try:
        await users_admin.get_user(conn, user_name)
    except users_admin.UserNotFound:
        raise HTTPException(status_code=404, detail=f"no user {user_name}")
    return await users_admin.user_permissions(conn, user_name)


@router.put("/users/{user_name}/permissions", response_model=dict[str, dict[str, bool]])
async def put_permissions(
    user_name: str, body: PermissionsIn, conn: Conn
) -> dict[str, dict[str, bool]]:
    try:
        await users_admin.set_permissions(conn, user_name, body.granted)
    except users_admin.UserNotFound:
        raise HTTPException(status_code=404, detail=f"no user {user_name}")
    except users_admin.BadPermission as exc:
        raise HTTPException(status_code=400, detail=f"unknown permission {exc}")
    return await users_admin.user_permissions(conn, user_name)
