from pathlib import Path

import pytest

from papi.services.operations.spreadsheets import (
    SpreadsheetError,
    is_spreadsheet,
    parse_csv_text,
    read_sheet,
)


def test_parse_csv_text_keys_rows_by_header_and_skips_blank_lines() -> None:
    sheet = parse_csv_text(
        'file_id,Operation,note\n1,AddFilesToTimepoint,"a, b"\n\n2,,\n'
    )
    assert sheet.columns == ["file_id", "Operation", "note"]
    assert sheet.rows == [
        {"file_id": "1", "Operation": "AddFilesToTimepoint", "note": "a, b"},
        {"file_id": "2", "Operation": "", "note": ""},
    ]
    assert sheet.named_operation == "AddFilesToTimepoint"


def test_named_operation_is_none_when_column_missing_or_blank() -> None:
    assert parse_csv_text("file_id\n1\n").named_operation is None
    assert parse_csv_text("file_id,Operation\n1,\n").named_operation is None
    with pytest.raises(SpreadsheetError):
        parse_csv_text("")


def test_read_sheet_handles_bom_and_latin1(tmp_path: Path) -> None:
    utf8 = tmp_path / "a.csv"
    utf8.write_bytes("﻿name\nZoë\n".encode("utf-8"))
    assert read_sheet(utf8).rows == [{"name": "Zoë"}]
    latin = tmp_path / "b.csv"
    latin.write_bytes("name\nZo\xeb\n".encode("latin-1"))
    assert read_sheet(latin).rows[0]["name"] in ("Zoë", "Zo�")  # chardet may guess


def test_is_spreadsheet_by_name_or_mime() -> None:
    assert is_spreadsheet("x.CSV", None)
    assert is_spreadsheet("x.xlsx", "application/octet-stream")
    assert is_spreadsheet("x.bin", "text/csv")
    assert not is_spreadsheet("x.dcm", "application/dicom")
