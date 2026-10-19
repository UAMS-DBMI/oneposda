from pathlib import Path

import asyncpg
import pytest

from papi.services.files import FileNotInDatabase, file_path, read_text_head


def test_read_text_head_truncates(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    target.write_bytes(b"hello\xffworld" * 10)

    head = read_text_head(target, max_bytes=5)

    assert head.text == "hello"
    assert head.truncated is True
    assert head.size == 110


def test_read_text_head_whole_file(tmp_path: Path) -> None:
    target = tmp_path / "small.txt"
    target.write_text("ok")

    head = read_text_head(target, max_bytes=1024)

    assert (head.text, head.truncated, head.size) == ("ok", False, 2)


async def test_unknown_file_id(conn: asyncpg.Connection) -> None:
    with pytest.raises(FileNotInDatabase):
        await file_path(conn, -1)
