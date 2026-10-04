"""Tests for the ported Posda::DB::Modules handlers.

These use a recording fake in place of the database, so they assert on the
statements each handler issues rather than on database state. The row-level
equivalence with the Perl is established separately by the differential
harness, which runs both implementations against real schemas.
"""

import io
import re
from contextlib import contextmanager

import pytest
from pydicom import dcmread
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

from posda.ingest import modules
from posda.ingest.values import ParsedValues


class FakeDb:
    """Records statements; returns canned rows for SELECTs."""

    def __init__(self, rows=None, keys=None):
        self.statements: list[tuple[str, list]] = []
        # rows: list of dicts returned by successive fetchone/fetchall calls
        self.rows = list(rows or [])
        self.keys = list(keys or [])
        self._next_key = 1

    def _record(self, sql, params):
        self.statements.append((" ".join(sql.split()), list(params)))

    def execute(self, sql, params=()):
        self._record(sql, params)

    def fetchone(self, sql, params=()):
        self._record(sql, params)
        return self.rows.pop(0) if self.rows else None

    def fetchall(self, sql, params=()):
        self._record(sql, params)
        rows = self.rows.pop(0) if self.rows else []
        return iter(rows)

    def insert_returning(self, sql, params, column):
        self._record(sql, params)
        if self.keys:
            return self.keys.pop(0)
        key = self._next_key
        self._next_key += 1
        return key

    @contextmanager
    def transaction(self):
        self.statements.append(("begin", []))
        try:
            yield
        except BaseException:
            self.statements.append(("rollback", []))
            raise
        else:
            self.statements.append(("commit", []))

    def inserts_into(self, table):
        pattern = re.compile(rf"^insert into {table}\b")
        return [(s, p) for s, p in self.statements if pattern.match(s)]


def build(**attrs) -> ParsedValues:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = "1.2.3"
    for key, value in attrs.items():
        setattr(ds, key, value)
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    buf.seek(0)
    return ParsedValues(dcmread(buf, force=True))


class TestSimpleInserts:
    def test_patient_maps_tob_to_time_ob(self):
        db = FakeDb()
        values = build(PatientName="Doe^John", PatientBirthDate="19700615")
        errors: list[str] = []
        modules.patient(db, values, 42, {}, errors)

        ((sql, params),) = db.inserts_into("file_patient")
        columns = sql.split("(")[1].split(")")[0].split(", ")
        assert columns[0] == "file_id" and params[0] == 42
        assert params[columns.index("patient_name")] == "Doe^John"
        assert params[columns.index("dob")] == "1970/06/15"
        # file_patient.time_ob is fed by the 'tob' parameter.
        assert "time_ob" in columns
        assert errors == []

    def test_ct_image_writes_all_sixteen_columns(self):
        db = FakeDb()
        values = build(KVP="120", ConvolutionKernel="STANDARD")
        modules.ct_image(db, values, 7, {}, [])

        ((sql, params),) = db.inserts_into("file_ct_image")
        assert len(params) == 17  # file_id + 16
        columns = sql.split("(")[1].split(")")[0].split(", ")
        assert params[columns.index("kvp")] == "120"
        assert params[columns.index("convolution_kernal")] == "STANDARD"


class TestSeries:
    def test_series_is_written_when_uid_present(self):
        db = FakeDb()
        values = build(SeriesInstanceUID="1.2.9", Modality="CT")
        errors: list[str] = []
        modules.series(db, values, 5, {}, errors)
        assert len(db.inserts_into("file_series")) == 1
        assert errors == []

    def test_series_without_uid_is_skipped_with_an_error(self):
        db = FakeDb()
        values = build(Modality="CT")
        errors: list[str] = []
        modules.series(db, values, 5, {}, errors)
        assert db.inserts_into("file_series") == []
        assert errors == ["Series instance UID undefined"]


class TestImagePixel:
    def test_missing_pixel_data_reports_and_stops(self):
        db = FakeDb()
        errors: list[str] = []
        modules.image_pixel(db, build(Rows=4), 1, {}, errors)
        assert errors == ["No pixel data in ImagePixel"]
        assert db.statements == []

    def test_large_pixel_data_skips_dedup_but_still_writes_image(self):
        # The live path: skip_large hides the pixel value, so
        # unique_pixel_data and pixel_location get nothing and the image row
        # carries a NULL unique_pixel_data_id.
        db = FakeDb(rows=[[]])
        hist: dict = {}
        values = build(Rows=4, Columns=4, BitsAllocated=8, PixelData=bytes(300))
        modules.image_pixel(db, values, 3, hist, [])

        assert db.inserts_into("unique_pixel_data") == []
        assert db.inserts_into("pixel_location") == []
        ((sql, params),) = db.inserts_into("image")
        columns = sql.split("(")[1].split(")")[0].split(", ")
        assert params[columns.index("unique_pixel_data_id")] is None
        assert len(db.inserts_into("file_image")) == 1
        assert hist["image_id"] is not None
        assert hist["unique_pixel_data_id"] is None

    def test_small_pixel_data_populates_dedup_tables(self):
        # Only reachable with skip_large disabled, but the code path is the
        # one the fix in the follow-up commit will re-enable.
        db = FakeDb(rows=[None, {"unique_pixel_data_id": 5}, []])
        values = build(Rows=4, Columns=4, BitsAllocated=8, PixelData=bytes(16))
        values.skip_large = 0
        hist: dict = {}
        modules.image_pixel(db, values, 3, hist, [])

        assert len(db.inserts_into("unique_pixel_data")) == 1
        ((sql, params),) = db.inserts_into("pixel_location")
        assert params[1] == 3
        assert isinstance(params[2], int)  # file offset


class TestWindowLevel:
    def test_requires_an_image_id(self):
        db = FakeDb()
        errors: list[str] = []
        modules.window_level(db, build(WindowCenter="45"), 1, {}, errors)
        assert errors == ["No image_id in WindowLevel"]

    def test_single_value_still_writes_because_dictionary_vm_boxes_it(self):
        # WindowCenter has dictionary VM 1-n, so a lone value arrives as a
        # list and the handler proceeds. A scalar here would drop the row.
        db = FakeDb(rows=[{"window_level_id": 5}, None])
        values = build(WindowCenter="45", WindowWidth="400")
        modules.window_level(db, values, 9, {"image_id": 100}, [])
        assert len(db.inserts_into("file_win_lev")) == 1

    def test_lookup_is_a_race_free_upsert(self):
        # The Perl's check-then-insert duplicated lookup rows under
        # concurrency; the port always writes ON CONFLICT instead.
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

    def test_multiple_values_write_one_row_each(self):
        db = FakeDb(rows=[{"window_level_id": 1}, None, {"window_level_id": 2}, None])
        values = build(WindowCenter="45\\50", WindowWidth="400\\500")
        modules.window_level(db, values, 9, {"image_id": 100}, [])
        rows = db.inserts_into("file_win_lev")
        assert [params[2] for _, params in rows] == [0, 1]

    def test_mismatched_lengths_are_ignored(self):
        db = FakeDb()
        values = build(WindowCenter="45\\50", WindowWidth="400")
        modules.window_level(db, values, 9, {"image_id": 100}, [])
        assert db.inserts_into("file_win_lev") == []

    def test_explanation_branch_reproduces_the_shadowed_loop_defect(self):
        # Two explanations means the inner loop runs twice over both values:
        # four file_win_lev rows for two window settings.
        db = FakeDb(rows=[{"window_level_id": 1}, None] * 4)
        values = build(
            WindowCenter="45\\50",
            WindowWidth="400\\500",
            WindowCenterWidthExplanation="BRAIN\\SUBDURAL",
        )
        modules.window_level(db, values, 9, {"image_id": 100}, [])
        rows = db.inserts_into("file_win_lev")
        assert len(rows) == 4
        assert [params[2] for _, params in rows] == [0, 1, 0, 1]


class TestSlopeIntercept:
    def test_requires_an_image_id(self):
        db = FakeDb()
        errors: list[str] = []
        modules.slope_intercept(db, build(), 1, {}, errors)
        assert errors == ["No image_id in SlopeIntercept"]

    def test_missing_slope_reports_and_stops(self):
        db = FakeDb()
        errors: list[str] = []
        modules.slope_intercept(db, build(), 4, {"image_id": 1}, errors)
        assert errors == ["no slope intercept for file 4"]

    def test_writes_lookup_and_links(self):
        db = FakeDb(rows=[{"slope_intercept_id": 5}, None])
        values = build(RescaleSlope="1", RescaleIntercept="-1024")
        modules.slope_intercept(db, values, 4, {"image_id": 11}, [])
        assert len(db.inserts_into("slope_intercept")) == 1
        assert len(db.inserts_into("image_slope_intercept")) == 1
        assert len(db.inserts_into("file_slope_intercept")) == 1

    def test_lookup_is_a_race_free_upsert(self):
        # The Perl's check-then-insert duplicated lookup rows under
        # concurrency; the port always writes ON CONFLICT instead.
        db = FakeDb(rows=[{"slope_intercept_id": 7}, None])
        values = build(RescaleSlope="1", RescaleIntercept="-1024")
        modules.slope_intercept(db, values, 4, {"image_id": 11}, [])
        assert any(
            s.startswith("insert into slope_intercept") and "on conflict" in s
            for s, _ in db.statements
        )
        assert not any(
            s.startswith("select * from slope_intercept") for s, _ in db.statements
        )

    def test_reuses_an_existing_image_link(self):
        # The upsert returns the surviving row's id; an image already linked
        # to it gets no second image_slope_intercept row.
        db = FakeDb(rows=[{"slope_intercept_id": 77}, {"x": 1}])
        values = build(RescaleSlope="1", RescaleIntercept="-1024")
        modules.slope_intercept(db, values, 4, {"image_id": 11}, [])
        assert db.inserts_into("image_slope_intercept") == []
        ((_, params),) = db.inserts_into("file_slope_intercept")
        assert params[0] == 77


class TestImagePlane:
    def test_requires_an_image_id(self):
        db = FakeDb()
        errors: list[str] = []
        modules.image_plane(db, build(), 1, {}, errors)
        assert errors == ["no image_id in ImagePlane"]

    def test_creates_geometry_then_links_the_file(self):
        db = FakeDb(rows=[None])
        values = build(
            ImageOrientationPatient=[1, 0, 0, 0, 1, 0],
            ImagePositionPatient=[-250.0, -250.0, 10.5],
            FrameOfReferenceUID="1.2.7",
        )
        modules.image_plane(db, values, 6, {"image_id": 12}, [])
        assert len(db.inserts_into("image_geometry")) == 1
        assert len(db.inserts_into("file_image_geometry")) == 1

    def test_reuses_existing_geometry(self):
        db = FakeDb(rows=[{"image_geometry_id": 55}])
        modules.image_plane(db, build(), 6, {"image_id": 12}, [])
        assert db.inserts_into("image_geometry") == []
        ((_, params),) = db.inserts_into("file_image_geometry")
        assert params == [6, 55]


class TestFrameOfReference:
    def test_writes_row_and_publishes_uid(self):
        db = FakeDb()
        hist: dict = {}
        modules.frame_of_reference(db, build(FrameOfReferenceUID="1.2.7"), 8, hist, [])
        ((_, params),) = db.inserts_into("file_for")
        assert params == [8, "1.2.7", None]
        assert hist["frame_of_reference"] == "1.2.7"


class TestRegistry:
    def test_every_stub_is_registered_and_harmless(self):
        db = FakeDb()
        for name in modules.STUBS:
            modules.HANDLERS[name](db, build(), 1, {}, [])
        assert db.statements == []

    @pytest.mark.parametrize(
        "name",
        ["Patient", "Study", "Series", "Equipment", "ImagePixel", "CTImage"],
    )
    def test_real_handlers_are_registered(self, name):
        assert callable(modules.HANDLERS[name])
