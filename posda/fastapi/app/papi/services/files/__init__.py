"""Locate Posda files on disk and read small text files for the UI."""

from dataclasses import dataclass
from pathlib import Path

import asyncpg

_PATH_SQL = """
    select root_path || '/' || rel_path as file_path
    from file
    natural join file_location
    natural join file_storage_root
    where file_id = $1
"""


class FileNotInDatabase(LookupError):
    """No file_location row exists for the file id."""


class FileMissingOnDisk(FileNotFoundError):
    """The database knows the file but it is not at the recorded path."""


@dataclass(frozen=True)
class TextHead:
    text: str
    truncated: bool
    size: int


async def file_path(conn: asyncpg.Connection, file_id: int) -> Path:
    raw = await conn.fetchval(_PATH_SQL, file_id)
    if raw is None:
        raise FileNotInDatabase(f"file {file_id} has no location")
    path = Path(raw)
    if not path.is_file():
        raise FileMissingOnDisk(f"file {file_id} is not at {path}")
    return path


def read_text_head(path: Path, max_bytes: int) -> TextHead:
    """Read up to ``max_bytes`` of a file as UTF-8, replacing bad bytes."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        data = handle.read(max_bytes)
    return TextHead(
        text=data.decode("utf-8", errors="replace"),
        truncated=size > len(data),
        size=size,
    )
