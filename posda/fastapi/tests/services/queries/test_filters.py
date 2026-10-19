from pathlib import Path

import pytest

from papi.services.queries.filters import (
    build_view,
    cell_text,
    compile_tests,
    existing_view,
    filter_key,
    normalise,
    row_matches,
)
from papi.services.queries.rowstore import RowStoreReader, RowStoreWriter

COLUMNS = ["id", "name", "tags"]


def test_regex_is_case_insensitive_and_anded() -> None:
    tests = compile_tests(COLUMNS, {"name": "^al", "tags": "b"})
    assert row_matches([1, "Alice", ["a", "b"]], tests)
    assert not row_matches([1, "Alice", ["a"]], tests)
    assert not row_matches([1, "Bob", ["b"]], tests)


def test_bad_regex_falls_back_to_literal() -> None:
    tests = compile_tests(COLUMNS, {"name": "a(b"})
    assert row_matches([1, "xxA(Byy", None], tests)
    assert not row_matches([1, "ab", None], tests)


def test_null_cells_match_as_empty_text() -> None:
    tests = compile_tests(COLUMNS, {"name": "^$"})
    assert row_matches([1, None, None], tests)
    assert cell_text(None) == ""
    assert cell_text(["x", None, 2]) == "{x,,2}"


def test_unknown_column_is_rejected() -> None:
    with pytest.raises(KeyError):
        compile_tests(COLUMNS, {"nope": "x"})


def test_normalise_drops_empty_patterns_and_key_tracks_rows() -> None:
    assert normalise({"name": "", "id": "1"}) == {"id": "1"}
    assert filter_key({"id": "1"}, 10) != filter_key({"id": "1"}, 11)
    assert filter_key({"a": "1", "b": "2"}, 1) == filter_key({"b": "2", "a": "1"}, 1)


def test_build_view_materialises_matching_rows_once(tmp_path: Path) -> None:
    writer = RowStoreWriter(tmp_path)
    writer.append_batch([i, f"name{i % 3}", None] for i in range(20))
    writer.close()

    view = build_view(tmp_path, COLUMNS, {"name": "name1"}, available=20)
    assert view.count == 7
    rows = RowStoreReader(tmp_path, view.name).rows(0, 100, available=view.count).rows
    assert all(r[1] == "name1" for r in rows)

    key = filter_key({"name": "name1"}, 20)
    assert existing_view(tmp_path, key) == view
    assert build_view(tmp_path, COLUMNS, {"name": "name1"}, available=20) == view
    # A different source count is a different view.
    assert build_view(tmp_path, COLUMNS, {"name": "name1"}, available=10).count == 3
