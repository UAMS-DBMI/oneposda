"""Uploading files from the browser into Posda (the Upload page).

Each file is stored under ``$POSDA_CACHE_ROOT/abc_uploads/<user>/<uuid>/``
with its original name, then imported the way the Perl GUI's
``ImportSingleFileIntoPosdaAndReturnId.pl`` did. Spreadsheets can then be
inspected (``/sheet``) and launched through ``/operations``.
"""

import asyncio
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from ...services.files import file_path, ingest
from ...services.operations import spreadsheets
from ...services.settings import get_settings
from .deps import Conn, CurrentUser

router = APIRouter()

IMPORT_COMMENT = "Importing Uploaded file into Posda"
CHUNK = 1 << 20


class UploadedOut(BaseModel):
    name: str
    size: int
    mime_type: str | None
    file_id: int
    created: bool
    is_spreadsheet: bool


class SheetOut(BaseModel):
    columns: list[str]
    row_count: int
    first_row: dict[str, str] | None
    named_operation: str | None


def _safe_name(name: str) -> str:
    base = Path(name or "upload").name
    return re.sub(r"[^\w.\-+ ()\[\]]", "_", base) or "upload"


async def _save(upload: UploadFile, directory: Path) -> tuple[Path, int]:
    target = directory / _safe_name(upload.filename or "")
    size = 0
    with target.open("wb") as handle:
        while chunk := await upload.read(CHUNK):
            handle.write(chunk)
            size += len(chunk)
    return target, size


@router.post("", response_model=list[UploadedOut], status_code=201)
async def upload_files(
    files: list[UploadFile], conn: Conn, user: CurrentUser
) -> list[UploadedOut]:
    if not files:
        raise HTTPException(status_code=400, detail="no files were uploaded")
    settings = get_settings()
    directory = settings.cache_root / "abc_uploads" / user.username / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    storage = ingest.Storage(settings.storage_root_id, settings.storage_root_path)
    results: list[UploadedOut] = []
    for upload in files:
        path, size = await _save(upload, directory)
        async with conn.transaction():
            ingested = await ingest.import_local_file(
                conn, path, storage, comment=IMPORT_COMMENT, localpath=str(path)
            )
        results.append(
            UploadedOut(
                name=path.name,
                size=size,
                mime_type=upload.content_type,
                file_id=ingested.file_id,
                created=ingested.created,
                is_spreadsheet=spreadsheets.is_spreadsheet(
                    path.name, upload.content_type
                ),
            )
        )
    return results


@router.get("/{file_id}/sheet", response_model=SheetOut)
async def sheet(file_id: int, conn: Conn) -> SheetOut:
    try:
        path = await file_path(conn, file_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        parsed = await asyncio.to_thread(spreadsheets.read_sheet, path)
    except spreadsheets.SpreadsheetError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return SheetOut(
        columns=parsed.columns,
        row_count=len(parsed.rows),
        first_row=parsed.rows[0] if parsed.rows else None,
        named_operation=parsed.named_operation,
    )
