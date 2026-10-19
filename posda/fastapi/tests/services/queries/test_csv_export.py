from datetime import UTC, datetime

from papi.services.queries.csv_export import (
    CSV_ROWS_PER_CHUNK,
    CsvHeader,
    csv_line,
    format_when,
    iter_csv,
    metadata_block,
)


def test_format_when_uses_perl_colon_layout_in_local_time() -> None:
    started = datetime(2026, 10, 18, 21, 5, 9, tzinfo=UTC)
    local = started.astimezone()
    assert format_when(started) == local.strftime("%Y-%m-%d:%H:%M:%S")
    assert format_when(started).count(":") == 3


def header(**overrides):
    base = dict(
        caption='Q(1, "two")',
        when="2026-10-18 21:00:00",
        who="abc-dev",
        columns=["a", "b"],
        filter_spec=None,
        unfiltered_rows=2,
        filtered_rows=None,
    )
    base.update(overrides)
    return CsvHeader(**base)


def test_csv_line_quotes_every_cell_and_pads_short_rows() -> None:
    assert csv_line(['say "hi"', None], 3) == '"say ""hi""","",""\r\n'
    assert csv_line([1, ["x", "y"]], 2) == '"1","{x,y}"\r\n'


def test_unfiltered_metadata_matches_perl_layout() -> None:
    assert metadata_block(header(), filtered=False) == (
        "Metadata:\r\n"
        "key,value\r\n"
        'query:,"Q(1, ""two"")"\r\n'
        "when:,2026-10-18 21:00:00\r\n"
        "by:,abc-dev\r\n"
        "rows: 2\r\n"
        "\r\n"
        "Query Data:\r\n"
        '"a","b"\r\n'
    )


def test_filtered_metadata_lists_filter_and_counts() -> None:
    block = metadata_block(
        header(filter_spec={"a": "x"}, filtered_rows=1), filtered=True
    )
    assert "unfiltered_rows:,2\r\nfiltered_rows:,1\r\n" in block
    assert 'filter:,"a contains ""x"";\n"\r\n\r\nFiltered Query Data:\r\n' in block


def test_iter_csv_chunks_rows() -> None:
    rows = ([i, "v"] for i in range(CSV_ROWS_PER_CHUNK + 1))
    chunks = list(iter_csv(header(), rows, filtered=False))
    assert len(chunks) == 3  # header, full chunk, remainder
    assert chunks[1].count("\r\n") == CSV_ROWS_PER_CHUNK
    assert chunks[2] == '"1000","v"\r\n'
