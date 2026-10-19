"""Per-column filters over a query result, built as a second row store.

A filter is ``{column: pattern}``. As in the Perl UI, each non-empty pattern
is a case-insensitive regex that must match the cell's text, and the
patterns are ANDed. A pattern that is not a valid regex is matched as a
literal substring instead of failing.

A filtered store is keyed by the filter and the number of source rows it was
built from, so paging through filtered results does not rescan the source and
a run that is still receiving rows gets a fresh filtered view once the count
changes. Building takes a file lock so two API workers asked for the same
view at once do the work once.
"""

import fcntl
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .rowstore import RowStoreReader, RowStoreWriter

Filter = dict[str, str]
CellTest = Callable[[str], bool]


def normalise(filter_spec: Filter | None) -> Filter:
    """Drop empty patterns; an empty filter means no filter at all."""
    if not filter_spec:
        return {}
    return {k: v for k, v in filter_spec.items() if v is not None and v != ""}


def filter_key(filter_spec: Filter, row_count: int) -> str:
    canonical = json.dumps(
        {"filter": dict(sorted(filter_spec.items())), "rows": row_count},
        sort_keys=True,
    )
    return hashlib.sha1(canonical.encode()).hexdigest()


def cell_text(value: Any) -> str:
    """The text a cell is matched (and displayed) as."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "{" + ",".join(cell_text(v) for v in value) + "}"
    return str(value)


def compile_test(pattern: str) -> CellTest:
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        needle = pattern.lower()
        return lambda text: needle in text.lower()
    return lambda text: regex.search(text) is not None


def compile_tests(
    columns: Sequence[str], filter_spec: Filter
) -> list[tuple[int, CellTest]]:
    index = {name: i for i, name in enumerate(columns)}
    tests: list[tuple[int, CellTest]] = []
    for column, pattern in normalise(filter_spec).items():
        if column not in index:
            raise KeyError(f"filter names unknown column {column!r}")
        tests.append((index[column], compile_test(pattern)))
    return tests


def row_matches(row: Sequence[Any], tests: Sequence[tuple[int, CellTest]]) -> bool:
    for column_index, test in tests:
        value = row[column_index] if column_index < len(row) else None
        if not test(cell_text(value)):
            return False
    return True


@dataclass(frozen=True)
class FilteredView:
    name: str
    count: int


def _count_path(directory: Path, name: str) -> Path:
    return directory / f"{name}.count"


def existing_view(directory: Path, key: str) -> FilteredView | None:
    name = f"filter-{key}"
    try:
        count = int(_count_path(directory, name).read_text())
    except FileNotFoundError:
        return None
    return FilteredView(name=name, count=count)


def build_view(
    directory: Path,
    columns: Sequence[str],
    filter_spec: Filter,
    *,
    available: int,
) -> FilteredView:
    """Materialise the filtered rows of ``rows`` under ``directory``.

    Blocking (file I/O and a lock); call it in a thread from async code.
    """
    key = filter_key(normalise(filter_spec), available)
    name = f"filter-{key}"
    lock_path = directory / f"{name}.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ready = existing_view(directory, key)
        if ready is not None:
            return ready
        tests = compile_tests(columns, filter_spec)
        source = RowStoreReader(directory)
        writer = RowStoreWriter(directory, name)
        try:
            matched = (
                r for r in source.iterate(available=available) if row_matches(r, tests)
            )
            count = writer.append_batch(matched)
        finally:
            writer.close()
        _count_path(directory, name).write_text(str(count))
        return FilteredView(name=name, count=count)
