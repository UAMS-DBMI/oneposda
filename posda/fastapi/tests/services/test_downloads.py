import io
import tarfile
from pathlib import Path

import pytest

from papi.services import downloads


def make_dir(cache_root: Path, name: str) -> Path:
    directory = downloads.download_root(cache_root) / name
    directory.mkdir(parents=True)
    (directory / "a.txt").write_text("hello")
    return directory


def test_list_dirs_skips_hidden_and_files(tmp_path: Path) -> None:
    make_dir(tmp_path, "collection_1")
    (downloads.download_root(tmp_path) / ".hidden").mkdir()
    (downloads.download_root(tmp_path) / "stray.txt").write_text("")
    found = downloads.list_dirs(tmp_path)
    assert [d.name for d in found] == ["collection_1"]
    assert found[0].entries == 1
    assert downloads.list_dirs(tmp_path / "missing") == []


def test_validate_name_rejects_traversal() -> None:
    assert downloads.validate_name("abc-1_x.y+z") == "abc-1_x.y+z"
    for bad in ("../x", "..", "/etc", ".hidden", "a/b", "", "a(b)"):
        with pytest.raises(downloads.BadDirectoryName):
            downloads.validate_name(bad)


async def test_tar_stream_follows_symlinks(tmp_path: Path) -> None:
    directory = make_dir(tmp_path, "d")
    target = tmp_path / "real.txt"
    target.write_text("linked")
    (directory / "link.txt").symlink_to(target)
    data = b"".join([chunk async for chunk in downloads.tar_stream(directory)])
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        # macOS bsdtar may add AppleDouble "._" entries; production is GNU tar.
        names = sorted(m.name for m in tar.getmembers() if "._" not in m.name)
        assert names == [".", "./a.txt", "./link.txt"]
        linked = tar.extractfile("./link.txt")
        assert linked is not None and linked.read() == b"linked"

    downloads.remove_dir(directory)
    assert not directory.exists()
    with pytest.raises(downloads.DownloadNotFound):
        downloads.resolve_dir(tmp_path, "d")
