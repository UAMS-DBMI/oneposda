from pathlib import Path

from papi.services.files import ingest


async def test_import_local_file_moves_new_files_and_reuses_existing(
    conn, tmp_path: Path
) -> None:
    storage = ingest.Storage(root_id=3, root_path=tmp_path / "created")
    source = tmp_path / "upload.csv"
    source.write_text("file_id\n1\n")

    first = await ingest.import_local_file(conn, source, storage, comment="test import")
    assert first.created is True
    assert not source.exists()
    stored = storage.root_path / ingest.storage_rel_path(first.digest)
    assert stored.read_text() == "file_id\n1\n"
    assert first.size == len("file_id\n1\n")

    row = await conn.fetchrow(
        "select f.size, f.ready_to_process, l.rel_path, l.file_storage_root_id "
        "from file f join file_location l using (file_id) where f.file_id = $1",
        first.file_id,
    )
    assert row["size"] == first.size
    assert row["ready_to_process"] is True
    assert row["file_storage_root_id"] == 3
    imports = await conn.fetchval(
        "select count(*) from file_import where file_id = $1", first.file_id
    )
    assert imports == 1

    again = tmp_path / "again.csv"
    again.write_text("file_id\n1\n")
    second = await ingest.import_local_file(conn, again, storage, comment="test import")
    assert second.created is False
    assert second.file_id == first.file_id
    assert again.exists()  # duplicates are left in place
