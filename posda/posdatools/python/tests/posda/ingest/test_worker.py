"""Tests for the file worker, pixel worker and parse layer."""

import io
import json

import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

from posda.ingest import parse, pixel_worker, worker
from posda.ingest.worker import FileJob

from test_modules import FakeDb

CT = "1.2.840.10008.5.1.4.1.1.2"


def write_dicom(tmp_path, name="t.dcm", pixel_data=None, **attrs):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = attrs.pop("media_sop_class", CTImageStorage)
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    ds.file_meta.ImplementationClassUID = "1.2.3.4.5"
    ds.SOPClassUID = attrs.pop("sop_class", CTImageStorage)
    ds.SOPInstanceUID = "1.2.3.4"
    ds.SeriesInstanceUID = "1.2.3.5"
    for key, value in attrs.items():
        setattr(ds, key, value)
    if pixel_data is not None:
        ds.Rows, ds.Columns, ds.BitsAllocated = 4, 4, 8
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.PixelRepresentation = 0
        ds.BitsStored, ds.HighBit = 8, 7
        ds.PixelData = pixel_data
    path = tmp_path / name
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    path.write_bytes(buf.getvalue())
    return str(path)


class TestFileJob:
    def test_round_trip_matches_the_perl_encoding(self):
        job = FileJob(file_id=7, path="/a/b.dcm")
        assert job.to_json() == '[7,"/a/b.dcm"]'
        assert FileJob.from_json(job.to_json()) == job

    def test_parses_payloads_produced_by_the_perl_daemon(self):
        assert FileJob.from_json(json.dumps([12, "/x.dcm"])) == FileJob(12, "/x.dcm")


class TestParse:
    def test_non_dicom_gets_a_file_type_from_file_1(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("hello\n")
        result = parse.parse(path)
        assert not result.is_dicom
        # The exact wording comes from file(1); assert on the shape only.
        assert result.file_type and "text" in result.file_type.lower()

    def test_dicom_is_parsed_with_meta(self, tmp_path):
        path = write_dicom(tmp_path, PatientID="PAT1")
        result = parse.parse(path)
        assert result.is_dicom
        assert result.status == parse.STATUS_PARSED
        assert result.meta.file_meta_version == 256
        assert result.meta.get("(0002,0010)") == ExplicitVRLittleEndian

    def test_data_set_start_and_size_follow_the_group_length(self, tmp_path):
        path = write_dicom(tmp_path)
        result = parse.parse(path)
        group_length = result.values.dataset.file_meta.FileMetaInformationGroupLength
        assert result.meta.data_set_start == 144 + group_length
        assert result.meta.data_set_size == result.length - result.meta.data_set_start

    def test_digest_and_length_match_the_file(self, tmp_path):
        import hashlib
        from pathlib import Path

        path = write_dicom(tmp_path)
        raw = Path(path).read_bytes()
        digest, length = parse.digest_and_length(path)
        assert digest == hashlib.md5(raw).hexdigest()
        assert length == len(raw)

    def test_metaheader_is_parsed_without_a_size_limit(self, tmp_path):
        # NewTry applies skip_large only after the meta group is read, so a
        # long meta value must survive even though the dataset limit is 256.
        path = write_dicom(tmp_path)
        result = parse.parse(path)
        assert result.meta.values.skip_large == 0
        assert result.values.skip_large == parse.SKIP_LARGE


class TestProcessFile:
    def test_missing_file_is_skipped(self, tmp_path):
        db = FakeDb()
        worker.process_file(db, FileJob(1, str(tmp_path / "nope.dcm")))
        assert db.statements == []

    def test_non_dicom_marks_the_row_and_stops(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("hello\n")
        db = FakeDb()
        worker.process_file(db, FileJob(2, str(path)))
        updates = [s for s, _ in db.statements if s.startswith("update file set")]
        assert len(updates) == 1
        assert "is_dicom_file = false" in updates[0]
        assert db.inserts_into("dicom_file") == []

    def test_dicom_writes_file_meta_and_dicom_file(self, tmp_path):
        path = write_dicom(tmp_path, PatientID="PAT1")
        db = FakeDb(rows=[[]] * 20)
        worker.process_file(db, FileJob(3, path))

        assert len(db.inserts_into("file_meta")) == 1
        ((sql, params),) = db.inserts_into("dicom_file")
        columns = sql.split("(")[1].split(")")[0].split(", ")
        assert params[columns.index("has_meta")] is True
        assert params[columns.index("has_sop_common")] is True
        assert params[columns.index("dicom_file_type")] == "CT Image Storage"

    def test_xfr_stx_is_always_null(self, tmp_path):
        # Posda::NewTry declares $xfr_stx and never assigns it. Confirmed
        # against the dev database: 0 of 1256 rows populated.
        path = write_dicom(tmp_path)
        db = FakeDb(rows=[[]] * 20)
        worker.process_file(db, FileJob(4, path))
        ((sql, params),) = db.inserts_into("dicom_file")
        columns = sql.split("(")[1].split(")")[0].split(", ")
        assert params[columns.index("xfr_stx")] is None

    def test_dicomdir_is_flagged_and_not_dispatched(self, tmp_path):
        path = write_dicom(
            tmp_path,
            media_sop_class="1.2.840.10008.1.3.10",
            sop_class="1.2.840.10008.1.3.10",
        )
        db = FakeDb(rows=[[]] * 20)
        worker.process_file(db, FileJob(5, path))
        ((sql, params),) = db.inserts_into("dicom_file")
        columns = sql.split("(")[1].split(")")[0].split(", ")
        assert params[columns.index("is_dicom_dir")] is True
        # DicomDir import is a stub in the Perl, so nothing else is written.
        assert db.inserts_into("file_patient") == []

    def test_unknown_sop_class_uses_the_uid_as_the_type(self, tmp_path):
        path = write_dicom(tmp_path, sop_class="9.9.9.9")
        db = FakeDb(rows=[[]] * 20)
        worker.process_file(db, FileJob(6, path))
        ((sql, params),) = db.inserts_into("dicom_file")
        columns = sql.split("(")[1].split(")")[0].split(", ")
        assert params[columns.index("dicom_file_type")] == "9.9.9.9"


class TestPixelWorker:
    def test_records_digest_offset_and_length(self, tmp_path):
        import hashlib

        pixels = bytes(range(16))
        path = write_dicom(tmp_path, pixel_data=pixels)
        db = FakeDb()
        pixel_worker.populate_pixel_info(db, FileJob(7, path))

        ((sql, params),) = [
            (s, p) for s, p in db.statements if "update dicom_file" in s
        ]
        assert "has_pixel_data = true" in sql
        assert params[0] == hashlib.md5(pixels).hexdigest()
        assert params[2] == len(pixels)
        assert params[3] == 7
        # The offset must point at the pixel bytes in the file.
        from pathlib import Path

        raw = Path(path).read_bytes()
        assert raw[params[1] : params[1] + len(pixels)] == pixels

    def test_file_without_pixels_is_marked_false(self, tmp_path):
        path = write_dicom(tmp_path)
        db = FakeDb()
        pixel_worker.populate_pixel_info(db, FileJob(8, path))
        ((sql, params),) = db.statements
        assert "has_pixel_data = false" in sql
        assert params == [8]

    def test_reads_large_pixel_data_that_the_file_worker_skips(self, tmp_path):
        # The whole point of the second pass: no size limit here.
        pixels = bytes(1024)
        path = write_dicom(tmp_path, pixel_data=pixels)
        db = FakeDb()
        pixel_worker.populate_pixel_info(db, FileJob(9, path))
        ((sql, params),) = db.statements
        assert "has_pixel_data = true" in sql
        assert params[2] == 1024

    def test_unparseable_file_is_skipped(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("hello\n")
        db = FakeDb()
        pixel_worker.populate_pixel_info(db, FileJob(10, str(path)))
        assert db.statements == []


class TestDeferredReads:
    """``parse`` must not load large elements into memory.

    Posda's parser seeks past anything over ``skip_large``; pydicom only
    matches that when ``dcmread`` is given ``defer_size``.
    """

    def test_large_elements_are_left_on_disk(self, tmp_path):
        path = write_dicom(tmp_path, pixel_data=bytes(1000))
        result = parse.parse(path)
        raw = result.values.dataset.get_item(0x7FE00010, keep_deferred=True)
        assert raw.value is None
        assert raw.length == 1000

    def test_small_elements_are_read(self, tmp_path):
        path = write_dicom(tmp_path, pixel_data=bytes(16))
        result = parse.parse(path)
        raw = result.values.dataset.get_item(0x7FE00010, keep_deferred=True)
        assert raw.value == bytes(16)

    def test_deferred_text_element_still_reads_as_skipped(self, tmp_path):
        # A deferred element must not be read back and converted to a str,
        # which would slip past the byte-length check.
        path = write_dicom(tmp_path, StudyDescription="X" * 300)
        assert parse.parse(path).values.get("(0008,1030)") is None

    def test_sequence_over_the_limit_is_still_navigable(self, tmp_path):
        from pydicom.sequence import Sequence

        item = Dataset()
        item.CodeMeaning = "Y" * 300
        path = write_dicom(tmp_path, ProcedureCodeSequence=Sequence([item]))
        values = parse.parse(path).values
        assert values.get("(0008,1032)[0](0008,0104)") is None
        values.skip_large = 0
        assert values.get("(0008,1032)[0](0008,0104)") == "Y" * 300

    def test_sequence_over_the_limit_reads_as_before(self, tmp_path):
        # Posda never size-limits a sequence, so deferral must not change
        # what a direct read of one returns.
        from pydicom import dcmread
        from pydicom.sequence import Sequence

        from posda.ingest.values import ParsedValues

        item = Dataset()
        item.CodeMeaning = "Y" * 300
        path = write_dicom(tmp_path, ProcedureCodeSequence=Sequence([item]))
        eager = ParsedValues(dcmread(path)).get("(0008,1032)")
        assert parse.parse(path).values.get("(0008,1032)") == eager

    def test_lifting_the_limit_after_parsing_reads_the_value(self, tmp_path):
        path = write_dicom(tmp_path, StudyDescription="X" * 300)
        values = parse.parse(path).values
        values.skip_large = 0
        assert values.get("(0008,1030)") == "X" * 300

    def test_no_limit_reads_everything(self, tmp_path):
        path = write_dicom(tmp_path, pixel_data=bytes(1000))
        result = parse.parse(path, skip_large=0)
        raw = result.values.dataset.get_item(0x7FE00010, keep_deferred=True)
        assert raw.value == bytes(1000)

    def test_metaheader_is_never_deferred(self, tmp_path):
        path = write_dicom(tmp_path, pixel_data=bytes(1000))
        result = parse.parse(path)
        for raw in result.meta.values.dataset.values():
            assert raw.value is not None
