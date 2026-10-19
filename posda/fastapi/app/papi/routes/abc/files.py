"""Small text views of Posda files (report emails, operation inputs)."""

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...services import files
from .deps import Conn, CurrentUser

router = APIRouter()

MAX_TEXT_BYTES = 5 * 1024 * 1024


class FileText(BaseModel):
    file_id: int
    text: str
    truncated: bool
    size: int


@router.get("/{file_id}/text", response_model=FileText)
async def read_file_text(
    file_id: int,
    conn: Conn,
    user: CurrentUser,
    max_bytes: int = Query(default=256 * 1024, ge=1, le=MAX_TEXT_BYTES),
) -> FileText:
    try:
        path = await files.file_path(conn, file_id)
    except files.FileNotInDatabase as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except files.FileMissingOnDisk as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    head = await asyncio.to_thread(files.read_text_head, path, max_bytes)
    return FileText(
        file_id=file_id, text=head.text, truncated=head.truncated, size=head.size
    )
