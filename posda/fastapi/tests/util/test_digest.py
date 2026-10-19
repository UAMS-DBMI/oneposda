import hashlib
from pathlib import Path

from papi.util.digest import md5sum_file


def test_md5sum_file_returns_total_size_and_digest(tmp_path: Path) -> None:
    data = b"x" * 20000  # longer than one 8 KiB read
    path = tmp_path / "blob"
    path.write_bytes(data)
    size, digest = md5sum_file(str(path))
    assert size == 20000
    assert digest == hashlib.md5(data).hexdigest()
