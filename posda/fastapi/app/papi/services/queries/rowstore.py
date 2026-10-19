"""Disk-backed storage for the rows of a query result.

A port of ``Posda::QueryRowStore``: rows are appended as one JSON array per
line to ``<name>.jsonl`` and a sparse index in ``<name>.idx`` records the byte
offset of every ``INDEX_STRIDE``-th row, so fetching a page seeks to the
nearest block and skips at most ``INDEX_STRIDE - 1`` lines.

Unlike the Perl store, writer and readers are usually different processes on
different hosts sharing the cache volume over NFS. Readers therefore reopen
the files on every call (close-to-open consistency) and never trust the file
length: the caller passes ``available``, the row count the writer committed to
the database, and reads stop there. A reader that finds the file shorter than
``available`` reports what it got as partial rather than failing.
"""

import json
import struct
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

INDEX_STRIDE = 256
_OFFSET = struct.Struct("<Q")


class RowStoreError(RuntimeError):
    """The store's files are missing or inconsistent."""


def _encode_value(value: Any) -> Any:
    """JSON-safe form of a cell, keeping the Perl UI's rendering of arrays."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_encode_value(v) for v in value]
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=True, default=str)
    return str(value)


def encode_row(row: Sequence[Any]) -> bytes:
    return (
        json.dumps([_encode_value(v) for v in row], ensure_ascii=True).encode() + b"\n"
    )


@dataclass
class Page:
    rows: list[list[Any]]
    partial: bool


class RowStoreWriter:
    """Append-only writer; one per run, owned by the process executing it."""

    def __init__(self, directory: Path, name: str = "rows") -> None:
        self.rows_path = directory / f"{name}.jsonl"
        self.index_path = directory / f"{name}.idx"
        self._rows: BinaryIO = self.rows_path.open("wb")
        self._index: BinaryIO = self.index_path.open("wb")
        self.count = 0
        self._bytes_written = 0

    def append_batch(self, rows: Iterable[Sequence[Any]]) -> int:
        """Append rows, flush both files, and return the new row count."""
        for row in rows:
            if self.count % INDEX_STRIDE == 0:
                self._index.write(_OFFSET.pack(self._bytes_written))
            line = encode_row(row)
            self._rows.write(line)
            self._bytes_written += len(line)
            self.count += 1
        # Index first: a reader that sees a row must be able to find its block.
        self._index.flush()
        self._rows.flush()
        return self.count

    def close(self) -> None:
        self._rows.close()
        self._index.close()


class RowStoreReader:
    """Random and sequential access to a store written by any process."""

    def __init__(self, directory: Path, name: str = "rows") -> None:
        self.rows_path = directory / f"{name}.jsonl"
        self.index_path = directory / f"{name}.idx"

    def _block_offsets(self) -> list[int]:
        try:
            data = self.index_path.read_bytes()
        except FileNotFoundError as exc:
            raise RowStoreError(f"no index at {self.index_path}") from exc
        usable = len(data) - len(data) % _OFFSET.size
        return [off for (off,) in _OFFSET.iter_unpack(data[:usable])]

    def _open_at(self, index: int, offsets: list[int]) -> BinaryIO:
        """A fresh handle positioned at row ``index``."""
        try:
            handle = self.rows_path.open("rb")
        except FileNotFoundError as exc:
            raise RowStoreError(f"no rows at {self.rows_path}") from exc
        block = min(index // INDEX_STRIDE, len(offsets) - 1)
        if block < 0:
            return handle
        handle.seek(offsets[block])
        for _ in range(index - block * INDEX_STRIDE):
            if not handle.readline():
                break
        return handle

    def rows(self, first: int, n: int, *, available: int) -> Page:
        """Up to ``n`` rows from ``first``, clamped to ``available``."""
        first = max(first, 0)
        if n <= 0 or first >= available:
            return Page(rows=[], partial=False)
        wanted = min(n, available - first)
        offsets = self._block_offsets()
        out: list[list[Any]] = []
        with self._open_at(first, offsets) as handle:
            for _ in range(wanted):
                line = handle.readline()
                if not line.endswith(b"\n"):
                    break
                out.append(json.loads(line))
        return Page(rows=out, partial=len(out) < wanted)

    def iterate(self, *, available: int) -> Iterator[list[Any]]:
        """Stream rows 0..available-1 (fewer if the file is still catching up)."""
        if available <= 0:
            return
        with self._open_at(0, self._block_offsets()) as handle:
            for _ in range(available):
                line = handle.readline()
                if not line.endswith(b"\n"):
                    return
                yield json.loads(line)

    def exists(self) -> bool:
        return self.rows_path.exists() and self.index_path.exists()
