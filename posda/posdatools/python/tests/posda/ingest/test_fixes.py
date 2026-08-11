"""Tests for the opt-in defect corrections.

Each defect is checked in both modes: reproduced by default (which is what
keeps the differential harness at zero differences) and corrected when the
flag is on.
"""

import io

import pytest
from pydicom import dcmread
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

from posda.ingest import fixes, iod, modules, parse, worker
from posda.ingest.fixes import Fixes
from posda.ingest.values import ParsedValues
from posda.ingest.worker import FileJob

from test_modules import FakeDb

CT = "1.2.840.10008.5.1.4.1.1.2"


@pytest.fixture
def enable(monkeypatch):
    """Turn individual fixes on for the duration of a test."""

    def _enable(**flags):
        monkeypatch.setattr(fixes, "ACTIVE", Fixes(**flags))
        for module in (worker, iod, modules, parse):
            monkeypatch.setattr(module.fixes, "ACTIVE", Fixes(**flags))

    return _enable


def write_dicom(tmp_path, name="t.dcm", **attrs):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    ds.file_meta.ImplementationClassUID = "1.2.3.4.5"
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = "1.2.3.4"
    for key, value in attrs.items():
        setattr(ds, key, value)
    path = tmp_path / name
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    path.write_bytes(buf.getvalue())
    return str(path)


def build(**attrs) -> ParsedValues:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = "1.2.3.4"
    for key, value in attrs.items():
        setattr(ds, key, value)
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    buf.seek(0)
    return ParsedValues(dcmread(buf, force=True))


def column_value(db, table, column):
    ((sql, params),) = db.inserts_into(table)
    columns = sql.split("(")[1].split(")")[0].split(", ")
    return params[columns.index(column)]


class TestConfig:
    def test_everything_is_off_by_default(self):
        assert Fixes().enabled_names() == []
        assert not Fixes().any_enabled

    def test_read_from_environment(self):
        got = Fixes.from_env({"POSDA_INGEST_FIX_XFR_STX": "true"})
        assert got.xfr_stx is True
        assert got.window_level_duplication is False

    @pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
    def test_truthy_spellings(self, value):
        assert Fixes.from_env({"POSDA_INGEST_FIX_XFR_STX": value}).xfr_stx

    @pytest.mark.parametrize("value", ["0", "false", "", "no"])
    def test_falsy_spellings(self, value):
        assert not Fixes.from_env({"POSDA_INGEST_FIX_XFR_STX": value}).xfr_stx


class TestXfrStx:
    def test_null_by_default(self, tmp_path):
        db = FakeDb(rows=[[]] * 20)
        worker.process_file(db, FileJob(1, write_dicom(tmp_path)))
        assert column_value(db, "dicom_file", "xfr_stx") is None

    def test_populated_when_enabled(self, tmp_path, enable):
        enable(xfr_stx=True)
        db = FakeDb(rows=[[]] * 20)
        worker.process_file(db, FileJob(1, write_dicom(tmp_path)))
        assert column_value(db, "dicom_file", "xfr_stx") == ExplicitVRLittleEndian


class TestOriginalSpecializedSopClass:
    def test_null_by_default(self):
        db = FakeDb(rows=[[]] * 8)
        values = build(OriginalSpecializedSOPClassUID=CT)
        iod.import_dataset(db, values, 1, CT, handlers={}, rt_runner=None)
        assert (
            column_value(db, "file_sop_common", "original_specialized_sop_class")
            is None
        )

    def test_populated_when_enabled(self, enable):
        enable(original_specialized_sop_class=True)
        db = FakeDb(rows=[[]] * 8)
        values = build(OriginalSpecializedSOPClassUID=CT)
        iod.import_dataset(db, values, 1, CT, handlers={}, rt_runner=None)
        assert (
            column_value(db, "file_sop_common", "original_specialized_sop_class") == CT
        )


class TestWindowLevelDuplication:
    def _run(self, db):
        values = build(
            WindowCenter="45\\50",
            WindowWidth="400\\500",
            WindowCenterWidthExplanation="BRAIN\\SUBDURAL",
        )
        modules.window_level(db, values, 9, {"image_id": 100}, [])

    def test_n_squared_by_default(self):
        db = FakeDb(rows=[None] * 12)
        self._run(db)
        rows = db.inserts_into("file_win_lev")
        assert [p[2] for _, p in rows] == [0, 1, 0, 1]

    def test_one_row_per_value_when_enabled(self, enable):
        enable(window_level_duplication=True)
        db = FakeDb(rows=[None] * 12)
        self._run(db)
        rows = db.inserts_into("file_win_lev")
        assert [p[2] for _, p in rows] == [0, 1]

    def test_files_without_an_explanation_are_unaffected(self, enable):
        # These take the else branch, which never had the defect.
        for flags in ({}, {"window_level_duplication": True}):
            enable(**flags)
            db = FakeDb(rows=[None] * 8)
            values = build(WindowCenter="45\\50", WindowWidth="400\\500")
            modules.window_level(db, values, 9, {"image_id": 100}, [])
            assert [p[2] for _, p in db.inserts_into("file_win_lev")] == [0, 1]


class TestLoadLargeValues:
    def test_long_value_dropped_by_default(self, tmp_path):
        path = write_dicom(tmp_path, StudyDescription="X" * 300)
        assert parse.parse(path).values.get("(0008,1030)") is None

    def test_long_value_kept_when_enabled(self, tmp_path, enable):
        enable(load_large_values=True)
        path = write_dicom(tmp_path, StudyDescription="X" * 300)
        assert parse.parse(path).values.get("(0008,1030)") == "X" * 300

    def test_explicit_argument_still_wins(self, tmp_path, enable):
        enable(load_large_values=True)
        path = write_dicom(tmp_path, StudyDescription="X" * 300)
        assert parse.parse(path, skip_large=256).values.get("(0008,1030)") is None

    def test_pixel_dedup_revives_when_enabled(self, tmp_path, enable):
        # The dedup tables are empty in production only because skip_large
        # hides the pixel value; lifting the limit restores them.
        enable(load_large_values=True)
        values = build(Rows=4, Columns=4, BitsAllocated=8, PixelData=bytes(300))
        values.skip_large = 0
        db = FakeDb(rows=[None, []])
        modules.image_pixel(db, values, 3, {}, [])
        assert len(db.inserts_into("unique_pixel_data")) == 1
        assert len(db.inserts_into("pixel_location")) == 1


class TestLookupUpsert:
    def test_check_then_insert_by_default(self):
        db = FakeDb(rows=[None, None])
        values = build(WindowCenter="45", WindowWidth="400")
        modules.window_level(db, values, 9, {"image_id": 100}, [])
        selects = [
            s for s, _ in db.statements if s.startswith("select * from window_level")
        ]
        assert len(selects) == 1
        assert not any("on conflict" in s for s, _ in db.statements)

    def test_upsert_when_enabled(self, enable):
        enable(lookup_upsert=True)
        db = FakeDb(rows=[{"window_level_id": 5}, None])
        values = build(WindowCenter="45", WindowWidth="400")
        modules.window_level(db, values, 9, {"image_id": 100}, [])
        assert any(
            s.startswith("insert into window_level") and "on conflict" in s
            for s, _ in db.statements
        )
        assert not any(
            s.startswith("select * from window_level") for s, _ in db.statements
        )

    def test_slope_intercept_upsert_when_enabled(self, enable):
        enable(lookup_upsert=True)
        db = FakeDb(rows=[{"slope_intercept_id": 7}, None])
        values = build(RescaleSlope="1", RescaleIntercept="-1024")
        modules.slope_intercept(db, values, 4, {"image_id": 11}, [])
        assert any(
            s.startswith("insert into slope_intercept") and "on conflict" in s
            for s, _ in db.statements
        )
        ((_, params),) = db.inserts_into("file_slope_intercept")
        assert params == [7, 4]
