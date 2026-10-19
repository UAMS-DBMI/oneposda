"""A small health view of the query runner for operators."""

import asyncio
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ...services.settings import get_settings
from .deps import Conn

router = APIRouter()


class StatusOut(BaseModel):
    runs_by_state: dict[str, int]
    active_owners: list[str]
    spool_bytes: int
    spool_dirs: int
    cache_root: str


def _spool_usage(root: Path) -> tuple[int, int]:
    spool = root / "query_runs"
    if not spool.is_dir():
        return 0, 0
    total = 0
    dirs = 0
    for entry in spool.iterdir():
        if entry.is_dir():
            dirs += 1
            total += sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
    return total, dirs


@router.get("", response_model=StatusOut)
async def status(conn: Conn) -> StatusOut:
    rows = await conn.fetch("select state, count(*) as n from query_run group by state")
    owners = await conn.fetch(
        "select distinct owner from query_run where state in ('running', 'paused') "
        "and owner is not null order by owner"
    )
    settings = get_settings()
    spool_bytes, spool_dirs = await asyncio.to_thread(_spool_usage, settings.cache_root)
    return StatusOut(
        runs_by_state={r["state"]: int(r["n"]) for r in rows},
        active_owners=[r["owner"] for r in owners],
        spool_bytes=spool_bytes,
        spool_dirs=spool_dirs,
        cache_root=str(settings.cache_root),
    )
