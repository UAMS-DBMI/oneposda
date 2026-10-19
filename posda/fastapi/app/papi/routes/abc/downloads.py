"""Directories prepared for download under the cache root."""

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...services import downloads
from ...services.settings import get_settings

router = APIRouter()


class DownloadDirOut(BaseModel):
    name: str
    modified: datetime
    entries: int


def _resolve(name: str):
    try:
        return downloads.resolve_dir(get_settings().cache_root, name)
    except downloads.BadDirectoryName:
        raise HTTPException(status_code=400, detail="bad directory name")
    except downloads.DownloadNotFound:
        raise HTTPException(status_code=404, detail=f"no download directory {name}")


@router.get("", response_model=list[DownloadDirOut])
async def list_dirs() -> list[DownloadDirOut]:
    found = await asyncio.to_thread(downloads.list_dirs, get_settings().cache_root)
    return [DownloadDirOut(**d.__dict__) for d in found]


@router.get("/{name}/tar")
async def download_tar(name: str) -> StreamingResponse:
    directory = _resolve(name)
    return StreamingResponse(
        downloads.tar_stream(directory),
        media_type="application/x-tar",
        headers={"Content-Disposition": f'attachment; filename="{name}.tar"'},
    )


@router.delete("/{name}", status_code=204)
async def delete_dir(name: str) -> None:
    directory = _resolve(name)
    await asyncio.to_thread(downloads.remove_dir, directory)
