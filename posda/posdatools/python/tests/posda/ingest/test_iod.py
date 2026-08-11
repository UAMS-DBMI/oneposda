"""Tests for the SOP-class dispatch ported from Posda::DB::DicomIod."""

import io

import pytest
from pydicom import dcmread
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

from posda.ingest import iod, modules
from posda.ingest.values import ParsedValues

from test_modules import FakeDb

CT = "1.2.840.10008.5.1.4.1.1.2"


def build(**attrs) -> ParsedValues:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    ds.SOPClassUID = attrs.pop("sop_class", CTImageStorage)
    ds.SOPInstanceUID = attrs.pop("sop_instance", "1.2.3.4")
    for key, value in attrs.items():
        setattr(ds, key, value)
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    buf.seek(0)
    return ParsedValues(dcmread(buf, force=True))


class TestTable:
    def test_table_is_complete(self):
        assert len(iod.SOP_HANDLERS) == 81
        assert sum(len(e.handlers) for e in iod.SOP_HANDLERS.values()) == 478

    def test_only_rt_handlers_are_unimplemented_in_python(self):
        referenced = {n for e in iod.SOP_HANDLERS.values() for n in e.handlers}
        assert referenced - set(modules.HANDLERS) == set(iod.RT_HANDLERS)

    def test_ct_handler_order_puts_image_pixel_before_its_dependents(self):
        handlers = iod.SOP_HANDLERS[CT].handlers
        pixel = handlers.index("ImagePixel")
        for dependent in ("ImagePlane", "SlopeIntercept", "WindowLevel"):
            assert handlers.index(dependent) > pixel


class TestSopClassDescription:
    def test_uses_datadict_spelling_not_the_handler_table_name(self):
        # DicomIod.pm calls this 'Xray Angiographic Image Storage'; the
        # column gets DataDict.pm's spelling.
        uid = "1.2.840.10008.5.1.4.1.1.12.1"
        assert iod.SOP_HANDLERS[uid].name == "Xray Angiographic Image Storage"
        assert iod.sop_class_description(uid) == "X-Ray Angiographic Image Storage"

    def test_known_class(self):
        assert iod.sop_class_description(CT) == "CT Image Storage"

    def test_unknown_class_falls_back_to_the_uid(self):
        assert iod.sop_class_description("9.9.9") == "9.9.9"


class TestImportDataset:
    def test_writes_sop_common_and_runs_handlers(self):
        db = FakeDb(rows=[[]] * 8)
        calls: list[str] = []
        registry = {
            name: (lambda *a, _n=name, **k: calls.append(_n))
            for name in iod.SOP_HANDLERS[CT].handlers
        }
        errors = iod.import_dataset(db, build(), 11, CT, handlers=registry)
        assert len(db.inserts_into("file_sop_common")) == 1
        assert calls == list(iod.SOP_HANDLERS[CT].handlers)
        assert errors == []

    def test_original_specialized_sop_class_is_always_null(self):
        # The Perl reads (0008,001b) into 'orig_spec_sop_class' but passes
        # $parms{original_specialized_sop_class} to the insert, so the column
        # can never be populated. Confirmed against the dev database.
        db = FakeDb(rows=[[]] * 8)
        values = build(OriginalSpecializedSOPClassUID="1.2.840.10008.5.1.4.1.1.2")
        iod.import_dataset(db, values, 11, CT, handlers={})
        ((sql, params),) = db.inserts_into("file_sop_common")
        columns = sql.split("(")[1].split(")")[0].split(", ")
        assert params[columns.index("original_specialized_sop_class")] is None

    def test_missing_sop_instance_reports_and_skips_handlers(self):
        db = FakeDb()
        ds = build().dataset
        del ds[0x00080018]
        calls: list[str] = []
        errors = iod.import_dataset(
            db,
            ParsedValues(ds),
            12,
            CT,
            handlers={"Patient": lambda *a, **k: calls.append("Patient")},
        )
        assert errors == ["file 12 has no SOP instance"]
        assert calls == []
        assert db.inserts_into("file_sop_common") == []
        assert len(db.inserts_into("dicom_process_errors")) == 1

    def test_unknown_sop_class_records_an_error(self):
        db = FakeDb(rows=[[]] * 4)
        errors = iod.import_dataset(db, build(), 13, "9.9.9", handlers={})
        assert errors == ['No handlers (or name) for "9.9.9"']

    def test_sop_class_with_a_space_is_repaired_and_redispatched(self):
        db = FakeDb(rows=[[]] * 8)
        calls: list[str] = []
        values = build(sop_class=f"{CT[:10]} {CT[10:]}")
        errors = iod.import_dataset(
            db,
            values,
            14,
            None,
            handlers={"Patient": lambda *a, **k: calls.append("Patient")},
        )
        assert errors[0].startswith("Sop class has a space")
        assert f'substitution: "{CT}"' in errors
        # The repaired UID drives handler lookup, so dispatch still happens.
        assert calls == ["Patient"]

    def test_errors_are_flushed_to_dicom_process_errors(self):
        db = FakeDb(rows=[[]] * 4)
        iod.import_dataset(db, build(), 15, "9.9.9", handlers={})
        rows = db.inserts_into("dicom_process_errors")
        assert len(rows) == 1
        assert rows[0][1][0] == 15


class TestCtpFile:
    def test_absent_ctp_tags_write_nothing(self):
        db = FakeDb(rows=[[]] * 8)
        iod.import_dataset(db, build(), 16, CT, handlers={})
        assert db.inserts_into("ctp_file") == []

    def test_ctp_project_name_triggers_the_row(self):
        db = FakeDb(rows=[[]] * 8)
        values = build()
        block = values.dataset.private_block(0x0013, "CTP", create=True)
        block.add_new(0x10, "LO", "MyProject")
        iod.import_dataset(db, values, 17, CT, handlers={})
        ((_, params),) = db.inserts_into("ctp_file")
        assert params[0] == 17
        assert params[1] == "MyProject"


class TestCreationDateTime:
    @pytest.mark.parametrize(
        "value,expected",
        [("143000", "14:30:00"), ("143000.5", "14:30:00.5")],
    )
    def test_valid_creation_times(self, value, expected):
        errors: list[str] = []
        assert iod._creation_time(value, errors) == expected
        assert errors == []

    def test_invalid_creation_time(self):
        errors: list[str] = []
        assert iod._creation_time("99", errors) is None
        assert errors == ['Illegal creation time: "99"']

    def test_valid_creation_date(self):
        errors: list[str] = []
        assert iod._creation_date("20240101", errors) == "2024/01/01"
        assert errors == []

    def test_out_of_range_creation_date(self):
        errors: list[str] = []
        assert iod._creation_date("20241301", errors) is None
        assert errors == ['Illegal creation date: "20241301"']

    def test_malformed_creation_date_uses_the_unquoted_message(self):
        # The two rejection paths in the Perl format their message
        # differently; only the range check quotes the value.
        errors: list[str] = []
        assert iod._creation_date("2024", errors) is None
        assert errors == ["Illegal creation date: 2024"]
