"""Reading an uploaded spreadsheet (CSV or XLSX) into rows keyed by column.

The Perl GUI converted uploads with ``CsvToPerlStruct.pl``; here CSV is read
with the ``csv`` module (encoding sniffed with chardet, as the import route
does for file names) and XLSX through the ``xlsx2csv`` tool in the image.
"""

import csv
import io
import subprocess
from dataclasses import dataclass
from pathlib import Path

import chardet

OPERATION_COLUMN = "Operation"
XLSX_SUFFIXES = (".xlsx", ".xlsm")


class SpreadsheetError(ValueError):
    pass


@dataclass(frozen=True)
class Sheet:
    columns: list[str]
    rows: list[dict[str, str]]

    @property
    def named_operation(self) -> str | None:
        """The operation named in the first data row's ``Operation`` column."""
        if not self.rows:
            return None
        name = (self.rows[0].get(OPERATION_COLUMN) or "").strip()
        return name or None


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        guess = chardet.detect(raw).get("encoding") or "latin-1"
        return raw.decode(guess, errors="replace")


def parse_csv_text(text: str) -> Sheet:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise SpreadsheetError("the spreadsheet is empty")
    columns = [c.strip() for c in header]
    rows = []
    for record in reader:
        if not any(cell.strip() for cell in record):
            continue
        rows.append(
            {
                col: (record[i] if i < len(record) else "")
                for i, col in enumerate(columns)
            }
        )
    return Sheet(columns=columns, rows=rows)


def _xlsx_to_csv(path: Path) -> str:
    result = subprocess.run(
        ["xlsx2csv", str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise SpreadsheetError(f"xlsx2csv failed: {result.stderr.strip()}")
    return result.stdout


def read_sheet(path: Path) -> Sheet:
    """Blocking; call in a thread from async code."""
    if path.suffix.lower() in XLSX_SUFFIXES:
        return parse_csv_text(_xlsx_to_csv(path))
    return parse_csv_text(_decode(path.read_bytes()))


def is_spreadsheet(filename: str, mime_type: str | None) -> bool:
    lower = filename.lower()
    if lower.endswith(".csv") or lower.endswith(XLSX_SUFFIXES):
        return True
    return mime_type in ("text/csv", "application/vnd.ms-excel")
