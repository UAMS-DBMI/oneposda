"""Activities: list, create, third-party URL, task status, timeline, timepoints."""

import datetime as dt

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, field_validator

from ...services import activities
from .deps import Conn, CurrentUser

router = APIRouter()


class ActivityOut(BaseModel):
    activity_id: int
    brief_description: str
    when_created: dt.datetime
    who_created: str
    when_closed: dt.datetime | None
    third_party_analysis_url: str | None


class NewActivity(BaseModel):
    brief_description: str

    @field_validator("brief_description")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("brief_description must not be blank")
        return value.strip()


class CreatedActivity(BaseModel):
    activity_id: int


class ThirdPartyUrl(BaseModel):
    third_party_analysis_url: str | None


class TaskStatusOut(BaseModel):
    subprocess_invocation_id: int
    operation_name: str | None
    start_time: dt.datetime
    last_updated: dt.datetime | None
    status_text: str | None
    expected_remaining_time: dt.timedelta | None
    end_time: dt.datetime | None
    since_update: dt.timedelta | None
    stale_warning: str | None


class TimepointOut(BaseModel):
    activity_timepoint_id: int
    when_created: dt.datetime
    comment: str | None
    creating_user: str | None
    file_count: int


class TimelineEventOut(BaseModel):
    inbox_content_id: int
    subprocess_invocation_id: int
    operation_name: str | None
    user_name: str
    started: dt.datetime
    ended: dt.datetime | None
    duration: dt.timedelta | None
    command_line: str | None
    email_file_id: int | None
    spreadsheet_file_id: int | None
    timepoint_id: int | None
    timepoint_file_count: int | None
    overlap_count: int


def _activity_out(activity: activities.Activity) -> ActivityOut:
    return ActivityOut.model_validate(activity, from_attributes=True)


@router.get("", response_model=list[ActivityOut])
async def list_activities(
    conn: Conn,
    user: CurrentUser,
    include_closed: bool = False,
    filter: str | None = Query(default=None, description="regex on description"),
) -> list[ActivityOut]:
    found = await activities.list_activities(
        conn, include_closed=include_closed, description_filter=filter
    )
    return [_activity_out(a) for a in found]


@router.post("", response_model=CreatedActivity, status_code=201)
async def create_activity(
    body: NewActivity, conn: Conn, user: CurrentUser
) -> CreatedActivity:
    activity_id = await activities.create_activity(
        conn, body.brief_description, user.username
    )
    return CreatedActivity(activity_id=activity_id)


@router.get("/{activity_id}", response_model=ActivityOut)
async def read_activity(activity_id: int, conn: Conn, user: CurrentUser) -> ActivityOut:
    try:
        return _activity_out(await activities.get_activity(conn, activity_id))
    except activities.ActivityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{activity_id}", status_code=204)
async def update_activity(
    activity_id: int, body: ThirdPartyUrl, conn: Conn, user: CurrentUser
) -> Response:
    url = body.third_party_analysis_url or None
    try:
        await activities.set_third_party_url(conn, activity_id, url)
    except activities.ActivityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/{activity_id}/task-status", response_model=list[TaskStatusOut])
async def read_task_status(
    activity_id: int, conn: Conn, user: CurrentUser
) -> list[TaskStatusOut]:
    rows = await activities.list_task_status(conn, activity_id)
    return [TaskStatusOut.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/{activity_id}/task-status/{subprocess_invocation_id}/dismiss", status_code=204
)
async def dismiss_task_status(
    activity_id: int, subprocess_invocation_id: int, conn: Conn, user: CurrentUser
) -> Response:
    dismissed = await activities.dismiss_task_status(
        conn, activity_id, subprocess_invocation_id, user.username
    )
    if not dismissed:
        raise HTTPException(status_code=404, detail="no open task status to dismiss")
    return Response(status_code=204)


@router.get("/{activity_id}/timeline", response_model=list[TimelineEventOut])
async def read_timeline(
    activity_id: int, conn: Conn, user: CurrentUser
) -> list[TimelineEventOut]:
    events = await activities.activity_timeline(conn, activity_id)
    return [TimelineEventOut.model_validate(e, from_attributes=True) for e in events]


@router.get("/{activity_id}/timepoints", response_model=list[TimepointOut])
async def read_timepoints(
    activity_id: int, conn: Conn, user: CurrentUser
) -> list[TimepointOut]:
    timepoints = await activities.list_timepoints(conn, activity_id)
    return [TimepointOut.model_validate(t, from_attributes=True) for t in timepoints]
