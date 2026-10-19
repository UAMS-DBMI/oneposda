"""CSV download of a query run, byte-compatible with the Perl GUI's output.

The Perl ``DownloadTableFromNewQuery`` wrote a metadata block, a blank line,
a data heading, a quoted header row and then every cell quoted, all with
CRLF line ends. Downstream scripts read these files, so the layout is kept.
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .filters import Filter, cell_text

CSV_ROWS_PER_CHUNK = 1000


@dataclass(frozen=True)
class CsvHeader:
    caption: str
    when: str
    who: str
    columns: Sequence[str]
    filter_spec: Filter | None
    unfiltered_rows: int
    filtered_rows: int | None


def format_when(started: datetime) -> str:
    """Local time the way Dispatch::EventHandler::now printed it."""
    return started.astimezone().strftime("%Y-%m-%d:%H:%M:%S")


def _quote(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def csv_line(row: Sequence[Any], num_cols: int) -> str:
    """One record with exactly ``num_cols`` quoted cells."""
    cells = [cell_text(row[i]) if i < len(row) else "" for i in range(num_cols)]
    return ",".join(_quote(c) for c in cells) + "\r\n"


def metadata_block(header: CsvHeader, *, filtered: bool) -> str:
    lines = [
        "Metadata:",
        "key,value",
        f"query:,{_quote(header.caption)}",
        f"when:,{header.when}",
        f"by:,{header.who}",
    ]
    if header.filter_spec:
        lines.append(f"unfiltered_rows:,{header.unfiltered_rows}")
        lines.append(f"filtered_rows:,{header.filtered_rows}")
        text = "".join(f'{k} contains "{v}";\n' for k, v in header.filter_spec.items())
        lines.append(f"filter:,{_quote(text)}")
        lines.append("")
        lines.append("Filtered Query Data:" if filtered else "Unfiltered Query Data:")
    else:
        lines.append(f"rows: {header.unfiltered_rows}")
        lines.append("")
        lines.append("Query Data:")
    lines.append(",".join(_quote(c) for c in header.columns))
    return "\r\n".join(lines) + "\r\n"


def iter_csv(
    header: CsvHeader, rows: Iterable[Sequence[Any]], *, filtered: bool
) -> Iterator[str]:
    """The whole file as text chunks: the header, then rows in batches."""
    yield metadata_block(header, filtered=filtered)
    num_cols = len(header.columns)
    chunk: list[str] = []
    for row in rows:
        chunk.append(csv_line(row, num_cols))
        if len(chunk) >= CSV_ROWS_PER_CHUNK:
            yield "".join(chunk)
            chunk = []
    if chunk:
        yield "".join(chunk)
