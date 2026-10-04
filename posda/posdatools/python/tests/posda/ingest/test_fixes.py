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


class TestDocumentation:
    def test_every_flag_is_documented(self):
        """A flag nobody can find is a flag nobody will use.

        Keeps docs/programming/Ingest-Fixes.md honest: adding a fix without
        documenting it fails here.
        """
        import re
        from dataclasses import fields
        from pathlib import Path

        doc = (
            Path(__file__).resolve().parents[4] / "docs/programming/Ingest-Fixes.md"
        ).read_text()
        for spec in fields(Fixes):
            assert spec.name.upper() in doc, f"{spec.name} is undocumented"


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
        iod.import_dataset(db, values, 1, CT, handlers={})
        assert (
            column_value(db, "file_sop_common", "original_specialized_sop_class")
            is None
        )

    def test_populated_when_enabled(self, enable):
        enable(original_specialized_sop_class=True)
        db = FakeDb(rows=[[]] * 8)
        values = build(OriginalSpecializedSOPClassUID=CT)
        iod.import_dataset(db, values, 1, CT, handlers={})
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
        db = FakeDb(rows=[{"window_level_id": 1}, None] * 4)
        self._run(db)
        rows = db.inserts_into("file_win_lev")
        assert [p[2] for _, p in rows] == [0, 1, 0, 1]

    def test_one_row_per_value_when_enabled(self, enable):
        enable(window_level_duplication=True)
        db = FakeDb(rows=[{"window_level_id": 1}, None] * 4)
        self._run(db)
        rows = db.inserts_into("file_win_lev")
        assert [p[2] for _, p in rows] == [0, 1]

    def test_files_without_an_explanation_are_unaffected(self, enable):
        # These take the else branch, which never had the defect.
        for flags in ({}, {"window_level_duplication": True}):
            enable(**flags)
            db = FakeDb(rows=[{"window_level_id": 1}, None] * 2)
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
        db = FakeDb(rows=[None, {"unique_pixel_data_id": 1}, []])
        modules.image_pixel(db, values, 3, {}, [])
        assert len(db.inserts_into("unique_pixel_data")) == 1
        assert len(db.inserts_into("pixel_location")) == 1


class ExplodingDb(FakeDb):
    """A FakeDb that raises on the first statement matching a fragment."""

    def __init__(self, explode_on, **kwargs):
        super().__init__(**kwargs)
        self.explode_on = explode_on

    def execute(self, sql, params=()):
        if self.explode_on in sql:
            raise RuntimeError("boom")
        super().execute(sql, params)


class TestAtomicImport:
    def _process(self, tmp_path, db, **attrs):
        path = write_dicom(tmp_path, **attrs)
        worker.process_file(db, FileJob(42, path))

    def test_partial_rows_survive_by_default(self, tmp_path):
        # The Perl's autocommit behaviour: everything before the failing
        # statement stays, nothing marks the file failed.
        db = ExplodingDb("insert into file_study", rows=[[]] * 20)
        with pytest.raises(RuntimeError):
            self._process(tmp_path, db)
        assert not any(s == "begin" for s, _ in db.statements)
        assert len(db.inserts_into("file_patient")) == 1
        assert not any("ready_to_process" in s for s, _ in db.statements)

    def test_failure_rolls_back_and_poisons_the_file(self, tmp_path, enable):
        enable(atomic_import=True)
        db = ExplodingDb("insert into file_study", rows=[[]] * 20)
        with pytest.raises(RuntimeError):
            self._process(tmp_path, db)

        statements = [s for s, _ in db.statements]
        assert "begin" in statements and "rollback" in statements
        # Everything after the rollback is the follow-up recording step.
        after = db.statements[statements.index("rollback") + 1 :]
        assert any(
            s.startswith("insert into dicom_process_errors")
            and "rows rolled back" in p[1]
            for s, p in after
        )
        assert ("update file set ready_to_process = false where file_id = %s",
                [42]) in after

    def test_accumulated_errors_survive_the_rollback(self, tmp_path, enable):
        # Patient runs before the exploding Study insert and complains about
        # the bad birth date; that complaint must still reach
        # dicom_process_errors after the rollback discards its first write.
        enable(atomic_import=True)
        db = ExplodingDb("insert into file_study", rows=[[]] * 20)
        with pytest.raises(RuntimeError):
            self._process(tmp_path, db, PatientBirthDate="bad")

        statements = [s for s, _ in db.statements]
        after = db.statements[statements.index("rollback") + 1 :]
        assert any(
            s.startswith("insert into dicom_process_errors") and "Bad date" in p[1]
            for s, p in after
        )

    def test_success_commits_and_does_not_poison(self, tmp_path, enable):
        enable(atomic_import=True)
        db = FakeDb(rows=[[]] * 20)
        self._process(tmp_path, db)
        statements = [s for s, _ in db.statements]
        assert "commit" in statements and "rollback" not in statements
        assert not any("ready_to_process" in s for s in statements)
        assert len(db.inserts_into("dicom_file")) == 1
