"""Tests for the RT handler bridge to Perl."""

import io
import json

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian

from posda.ingest import iod, rt_bridge
from posda.ingest.values import ParsedValues

from test_modules import FakeDb

RT_PLAN = "1.2.840.10008.5.1.4.1.1.481.5"
RT_DOSE = "1.2.840.10008.5.1.4.1.1.481.2"
RT_STRUCT = "1.2.840.10008.5.1.4.1.1.481.3"


def build(sop_class: str, path: str | None = "/tmp/x.dcm") -> ParsedValues:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = sop_class
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = "1.2.3.4"
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    buf.seek(0)
    from pydicom import dcmread

    return ParsedValues(dcmread(buf, force=True), source_path=path)


class RecordingRunner:
    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, values, file_id, handlers, hist, errors):
        self.calls.append((file_id, list(handlers), dict(hist)))


class TestBlockBatching:
    def test_rt_plan_block_is_dispatched_in_one_call(self):
        runner = RecordingRunner()
        db = FakeDb(rows=[[]] * 20)
        iod.import_dataset(
            db, build(RT_PLAN), 1, RT_PLAN, handlers={}, rt_runner=runner
        )
        assert len(runner.calls) == 1
        _, handlers, _ = runner.calls[0]
        # RtBrachy is a print-only stub in the Perl, so it stays on the
        # Python side and is not part of the block.
        assert handlers == [
            "RtPlan",
            "RtPrescription",
            "RtToleranceTables",
            "RtPatientSetup",
            "RtFractionScheme",
            "RtBeams",
        ]

    def test_structure_set_no_longer_uses_the_bridge(self):
        # StructureSet, RoiContour and RtRoiObservations are native now, so
        # nothing in an RT Structure Set goes to Perl.
        runner = RecordingRunner()
        db = FakeDb(rows=[[]] * 20)
        iod.import_dataset(
            db, build(RT_STRUCT), 2, RT_STRUCT, handlers={}, rt_runner=runner
        )
        assert runner.calls == []

    def test_rt_dose_no_longer_uses_the_bridge(self):
        # RTDose and RTDvh are native now; image_id reaches RTDose directly
        # through hist rather than being forwarded across a process.
        runner = RecordingRunner()
        db = FakeDb(rows=[[]] * 20)
        iod.import_dataset(
            db, build(RT_DOSE), 3, RT_DOSE, handlers={}, rt_runner=runner
        )
        assert runner.calls == []

    def test_non_rt_sop_class_never_calls_the_bridge(self):
        runner = RecordingRunner()
        db = FakeDb(rows=[[]] * 20)
        ct = "1.2.840.10008.5.1.4.1.1.2"
        iod.import_dataset(db, build(ct), 4, ct, handlers={}, rt_runner=runner)
        assert runner.calls == []

    def test_rt_runner_none_skips_the_block_entirely(self):
        db = FakeDb(rows=[[]] * 20)
        errors = iod.import_dataset(
            db, build(RT_PLAN), 5, RT_PLAN, handlers={}, rt_runner=None
        )
        assert errors == []


class TestRunHandlers:
    def test_empty_handler_list_is_a_no_op(self):
        assert rt_bridge.run_handlers(1, "/x.dcm", [], {}) == []

    def test_missing_source_path_is_reported(self):
        errors: list[str] = []
        rt_bridge.run_block(build(RT_PLAN, path=None), 6, ["RtPlan"], {}, errors)
        assert len(errors) == 1
        assert "no source path" in errors[0]

    def test_only_image_id_is_forwarded(self, monkeypatch):
        captured = {}

        def fake_run(cmd, input, capture_output, text, timeout, check):
            captured["request"] = json.loads(input)

            class Result:
                stdout = '{"errors":[],"hist":{}}'
                stderr = ""
                returncode = 0

            return Result()

        monkeypatch.setattr(rt_bridge.subprocess, "run", fake_run)
        monkeypatch.setattr(rt_bridge, "bridge_path", lambda: "/bin/true")

        hist = {"image_id": 9, "roi": {"internal": "structure"}, "plan_id": 3}
        rt_bridge.run_handlers(7, "/x.dcm", ["RTDose"], hist)
        assert captured["request"]["hist"] == {"image_id": 9}

    def test_errors_are_returned_not_swallowed(self, monkeypatch):
        def fake_run(cmd, input, capture_output, text, timeout, check):
            class Result:
                stdout = '{"errors":["boom"],"hist":{"plan_id":5}}'
                stderr = ""
                returncode = 0

            return Result()

        monkeypatch.setattr(rt_bridge.subprocess, "run", fake_run)
        monkeypatch.setattr(rt_bridge, "bridge_path", lambda: "/bin/true")

        hist: dict = {}
        assert rt_bridge.run_handlers(8, "/x.dcm", ["RtPlan"], hist) == ["boom"]
        assert hist["plan_id"] == 5

    def test_empty_response_is_reported(self, monkeypatch):
        def fake_run(cmd, input, capture_output, text, timeout, check):
            class Result:
                stdout = ""
                stderr = "perl exploded"
                returncode = 2

            return Result()

        monkeypatch.setattr(rt_bridge.subprocess, "run", fake_run)
        monkeypatch.setattr(rt_bridge, "bridge_path", lambda: "/bin/true")

        errors = rt_bridge.run_handlers(9, "/x.dcm", ["RtPlan"], {})
        assert len(errors) == 1
        assert "no response" in errors[0]

    def test_unparseable_response_is_reported(self, monkeypatch):
        def fake_run(cmd, input, capture_output, text, timeout, check):
            class Result:
                stdout = "not json"
                stderr = ""
                returncode = 0

            return Result()

        monkeypatch.setattr(rt_bridge.subprocess, "run", fake_run)
        monkeypatch.setattr(rt_bridge, "bridge_path", lambda: "/bin/true")

        errors = rt_bridge.run_handlers(10, "/x.dcm", ["RtPlan"], {})
        assert len(errors) == 1
        assert "unparseable response" in errors[0]
