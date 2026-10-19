from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from papi.services.queries.rowstore import (
    INDEX_STRIDE,
    RowStoreError,
    RowStoreReader,
    RowStoreWriter,
    encode_row,
)


def fill(directory: Path, n: int) -> RowStoreWriter:
    writer = RowStoreWriter(directory)
    writer.append_batch([i, f"row {i}", None] for i in range(n))
    return writer


def test_encode_row_stringifies_non_json_values_and_keeps_arrays() -> None:
    line = encode_row(
        [1, "é", Decimal("1.50"), date(2026, 1, 2), ["a", None], {"k": 1}]
    )
    assert (
        line == b'[1, "\\u00e9", "1.50", "2026-01-02", ["a", null], "{\\"k\\": 1}"]\n'
    )


def test_pages_across_index_blocks(tmp_path: Path) -> None:
    n = INDEX_STRIDE * 2 + 10
    writer = fill(tmp_path, n)
    reader = RowStoreReader(tmp_path)

    page = reader.rows(INDEX_STRIDE - 2, 5, available=writer.count)
    assert [r[0] for r in page.rows] == list(range(INDEX_STRIDE - 2, INDEX_STRIDE + 3))
    assert page.partial is False

    tail = reader.rows(n - 3, 10, available=writer.count)
    assert [r[0] for r in tail.rows] == [n - 3, n - 2, n - 1]
    assert reader.rows(n, 10, available=writer.count).rows == []
    assert reader.rows(-5, 2, available=writer.count).rows[0][0] == 0
    writer.close()


def test_reader_never_reads_past_available(tmp_path: Path) -> None:
    writer = fill(tmp_path, 50)
    reader = RowStoreReader(tmp_path)
    assert len(reader.rows(0, 100, available=20).rows) == 20
    assert len(list(reader.iterate(available=7))) == 7
    writer.close()


def test_reader_reports_partial_when_file_lags(tmp_path: Path) -> None:
    writer = fill(tmp_path, 5)
    reader = RowStoreReader(tmp_path)
    page = reader.rows(0, 10, available=8)  # the database says 8, the file has 5
    assert len(page.rows) == 5
    assert page.partial is True
    writer.close()


def test_rows_appended_later_become_visible(tmp_path: Path) -> None:
    writer = fill(tmp_path, 3)
    reader = RowStoreReader(tmp_path)
    assert len(reader.rows(0, 10, available=3).rows) == 3
    writer.append_batch([[9, "late", None]])
    assert reader.rows(3, 1, available=4).rows == [[9, "late", None]]
    writer.close()


def test_missing_store_raises(tmp_path: Path) -> None:
    with pytest.raises(RowStoreError):
        RowStoreReader(tmp_path).rows(0, 1, available=1)
