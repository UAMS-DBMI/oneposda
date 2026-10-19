"""Putting a file on disk into Posda: the ``file`` row, its location, and an
import record.

These are the steps ``routes/importer.py`` performed inline for uploads and
in-place imports. The ABC launcher needs the same steps for the spreadsheet
and input files it generates, on the same connection as the rest of the
launch so everything commits together.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from ...util.digest import md5sum_file


@dataclass(frozen=True)
class Storage:
    """Where imported files are copied: ``file_storage_root`` id and path."""

    root_id: int
    root_path: Path


@dataclass(frozen=True)
class Ingested:
    file_id: int
    created: bool
    digest: str
    size: int


def storage_rel_path(digest: str) -> str:
    return os.path.join(digest[:2], digest[2:4], digest[4:6], digest)


def copy_into_storage(source: Path, digest: str, storage: Storage) -> str:
    """Move ``source`` to its digest-addressed place; returns the rel path."""
    rel_path = storage_rel_path(digest)
    target = storage.root_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(source, target)
    return rel_path


async def create_or_get_file_id(
    conn: asyncpg.Connection, digest: str, size: int
) -> tuple[bool, int]:
    record = await conn.fetchrow(
        """
        insert into file (digest, size, processing_priority)
        values ($1, $2, 1)
        on conflict do nothing
        returning file_id
        """,
        digest,
        size,
    )
    if record is not None:
        return True, int(record["file_id"])
    existing = await conn.fetchrow("select file_id from file where digest = $1", digest)
    if existing is None:
        raise RuntimeError(f"file with digest {digest} neither inserted nor found")
    return False, int(existing["file_id"])


async def create_file_location(
    conn: asyncpg.Connection, file_id: int, root_id: int, rel_path: str
) -> None:
    await conn.execute(
        "insert into file_location (file_id, file_storage_root_id, rel_path) "
        "values ($1, $2, $3)",
        file_id,
        root_id,
        rel_path,
    )


async def set_ready_to_process(
    conn: asyncpg.Connection, file_id: int, ready: bool
) -> None:
    await conn.execute(
        "update file set ready_to_process = $2 where file_id = $1", file_id, ready
    )


async def create_import_event(
    conn: asyncpg.Connection,
    comment: str,
    origin: str | None = None,
    expected_count: int | None = None,
) -> int:
    return int(
        await conn.fetchval(
            """
            insert into import_event
              (import_type, import_comment, import_time, import_origin,
               import_expected_count)
            values ('posda-api import', $1, now(), $2, $3)
            returning import_event_id
            """,
            comment,
            origin,
            expected_count,
        )
    )


async def create_file_import(
    conn: asyncpg.Connection, file_id: int, import_event_id: int, localpath: str | None
) -> None:
    await conn.execute(
        "insert into file_import values ($1, $2, $3, $4, $5, now())",
        import_event_id,
        file_id,
        None,
        None,
        localpath,
    )


async def import_local_file(
    conn: asyncpg.Connection,
    path: Path,
    storage: Storage,
    *,
    comment: str,
    import_event_id: int | None = None,
    localpath: str | None = None,
) -> Ingested:
    """Import ``path`` by moving it into storage (if new) and recording it.

    ``path`` is consumed when the file is new; when the digest already exists
    the file is left where it is and the existing file_id is returned.
    Run inside the caller's transaction.
    """
    size, digest = md5sum_file(str(path))
    created, file_id = await create_or_get_file_id(conn, digest, size)
    if created:
        rel_path = copy_into_storage(path, digest, storage)
        await create_file_location(conn, file_id, storage.root_id, rel_path)
        await set_ready_to_process(conn, file_id, True)
    if import_event_id is None:
        import_event_id = await create_import_event(conn, comment)
    await create_file_import(conn, file_id, import_event_id, localpath or str(path))
    return Ingested(file_id=file_id, created=created, digest=digest, size=size)
