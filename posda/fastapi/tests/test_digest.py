"""md5sum_file must report the whole file's size, not its last chunk's.

    cd posda/fastapi/app && python -m pytest ../tests/test_digest.py
"""
import hashlib
import os

import pytest

from papi.util.digest import md5sum_file

CHUNK = 8192


@pytest.mark.parametrize(
    "size",
    [0, 1, CHUNK - 1, CHUNK, CHUNK + 1, 3 * CHUNK, 1183 * CHUNK + 2424],
)
def test_size_and_digest_cover_whole_file(tmp_path, size):
    data = os.urandom(size)
    path = tmp_path / "file.dcm"
    path.write_bytes(data)

    got_size, got_digest = md5sum_file(path)

    assert got_size == size
    assert got_digest == hashlib.md5(data).hexdigest()
