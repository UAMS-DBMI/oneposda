"""Directories prepared under ``$POSDA_CACHE_ROOT/linked_for_download``.

Operations such as MakeDownloadableDirectory build a directory of symlinks
there; the Download page lists them, streams one as a tar (following the
links, as ``tar -chf`` did) and deletes it afterwards.
"""

import asyncio
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DOWNLOAD_SUBDIR = "linked_for_download"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-+ ]*$")


class BadDirectoryName(ValueError):
    pass


class DownloadNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DownloadDir:
    name: str
    modified: datetime
    entries: int


def download_root(cache_root: Path) -> Path:
    return cache_root / DOWNLOAD_SUBDIR


def validate_name(name: str) -> str:
    if not _NAME.match(name) or ".." in name:
        raise BadDirectoryName(name)
    return name


def list_dirs(cache_root: Path) -> list[DownloadDir]:
    root = download_root(cache_root)
    if not root.is_dir():
        return []
    dirs = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        stat = entry.stat()
        dirs.append(
            DownloadDir(
                name=entry.name,
                modified=datetime.fromtimestamp(stat.st_mtime).astimezone(),
                entries=sum(1 for _ in entry.iterdir()),
            )
        )
    return dirs


def resolve_dir(cache_root: Path, name: str) -> Path:
    path = download_root(cache_root) / validate_name(name)
    if not path.is_dir():
        raise DownloadNotFound(name)
    return path


async def tar_stream(directory: Path, chunk_size: int = 1 << 16):
    """Yield a tar of ``directory`` (symlinks followed), as ``tar -chf - .``."""
    process = await asyncio.create_subprocess_exec(
        "tar",
        "-chf",
        "-",
        "-C",
        str(directory),
        ".",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        while chunk := await process.stdout.read(chunk_size):
            yield chunk
    finally:
        code = await process.wait()
        if code != 0 and process.stderr is not None:
            error = (await process.stderr.read()).decode(errors="replace")
            raise RuntimeError(f"tar exited {code}: {error.strip()}")


def remove_dir(directory: Path) -> None:
    shutil.rmtree(directory)
