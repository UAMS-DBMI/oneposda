"""The user's inbox of operation reports."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...services import inbox
from ...services.files import FileNotInDatabase, file_path, read_text_head
from .deps import Conn, CurrentUser

router = APIRouter()

REPORT_MAX_BYTES = 5 * 1024 * 1024


class InboxItemOut(BaseModel):
    user_inbox_content_id: int
    background_subprocess_report_id: int | None
    current_status: str | None
    date_entered: datetime | None
    date_dismissed: datetime | None
    operation_name: str | None
    report_name: str | None


class InboxOperationOut(BaseModel):
    operation_type: str | None
    when_occurred: datetime | None
    invoking_user: str | None
    how_invoked: str | None


class InboxItemDetailOut(InboxItemOut):
    file_id: int | None
    subprocess_invocation_id: int | None
    command_line: str | None
    invoking_user: str | None
    filed_activity_id: int | None
    text: str | None
    text_truncated: bool
    operations: list[InboxOperationOut]


class UnreadOut(BaseModel):
    unread: int


class ForwardIn(BaseModel):
    username: str


class FileIn(BaseModel):
    activity_id: int


def _item_out(item: inbox.InboxItem) -> InboxItemOut:
    return InboxItemOut(**{k: getattr(item, k) for k in InboxItemOut.model_fields})


async def _item(conn: Conn, user: CurrentUser, item_id: int) -> inbox.InboxItemDetail:
    try:
        return await inbox.get_item(conn, user.username, item_id)
    except inbox.InboxItemNotFound:
        raise HTTPException(status_code=404, detail=f"inbox item {item_id} not found")


@router.get("", response_model=list[InboxItemOut])
async def list_items(
    conn: Conn, user: CurrentUser, include_dismissed: bool = Query(default=False)
) -> list[InboxItemOut]:
    items = await inbox.list_items(
        conn, user.username, include_dismissed=include_dismissed
    )
    return [_item_out(i) for i in items]


@router.get("/unread-count", response_model=UnreadOut)
async def unread_count(conn: Conn, user: CurrentUser) -> UnreadOut:
    return UnreadOut(unread=await inbox.unread_count(conn, user.username))


@router.get("/users", response_model=list[str])
async def inbox_users(conn: Conn) -> list[str]:
    return await inbox.usernames(conn)


@router.get("/{item_id}", response_model=InboxItemDetailOut)
async def item_detail(
    item_id: int, conn: Conn, user: CurrentUser
) -> InboxItemDetailOut:
    """The item with its report text; viewing marks it read, as the Perl page did."""
    item = await _item(conn, user, item_id)
    text, truncated = None, False
    if item.file_id is not None:
        try:
            head = read_text_head(await file_path(conn, item.file_id), REPORT_MAX_BYTES)
            text, truncated = head.text, head.truncated
        except (FileNotInDatabase, OSError) as exc:
            text = f"(report file unavailable: {exc})"
    if item.current_status in inbox.UNREAD_STATUSES:
        await inbox.mark_read(conn, user.username, item_id)
    operations = await inbox.recent_operations(conn, item_id)
    return InboxItemDetailOut(
        **_item_out(item).model_dump(),
        file_id=item.file_id,
        subprocess_invocation_id=item.subprocess_invocation_id,
        command_line=item.command_line,
        invoking_user=item.invoking_user,
        filed_activity_id=item.filed_activity_id,
        text=text,
        text_truncated=truncated,
        operations=[InboxOperationOut(**op.__dict__) for op in operations],
    )


@router.post("/{item_id}/dismiss", status_code=204)
async def dismiss_item(item_id: int, conn: Conn, user: CurrentUser) -> None:
    await _item(conn, user, item_id)
    await inbox.dismiss(conn, user.username, item_id)


@router.post("/{item_id}/file", status_code=204)
async def file_item(item_id: int, body: FileIn, conn: Conn, user: CurrentUser) -> None:
    item = await _item(conn, user, item_id)
    if item.filed_activity_id is not None:
        raise HTTPException(
            status_code=409, detail="this message has already been filed"
        )
    exists = await conn.fetchval(
        "select 1 from activity where activity_id = $1", body.activity_id
    )
    if not exists:
        raise HTTPException(
            status_code=404, detail=f"activity {body.activity_id} does not exist"
        )
    await inbox.file_to_activity(conn, user.username, item_id, body.activity_id)


@router.post("/{item_id}/forward", response_model=InboxItemOut, status_code=201)
async def forward_item(
    item_id: int, body: ForwardIn, conn: Conn, user: CurrentUser
) -> InboxItemOut:
    item = await _item(conn, user, item_id)
    try:
        new_id = await inbox.forward(conn, user.username, item, body.username)
    except inbox.NoSuchInboxUser:
        raise HTTPException(status_code=404, detail=f"{body.username} has no inbox")
    return _item_out(await inbox.get_item(conn, body.username, new_id))
