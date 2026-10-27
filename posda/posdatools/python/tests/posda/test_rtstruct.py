"""Tests for the RTSTRUCT ROI checks in posda.rtstruct."""

import csv
import io
import re

from pydicom import dcmread
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian

from posda.rtstruct import (
    DELETE,
    EDIT_SHEET_HEADER,
    INVENTORY_HEADER,
    REPORT,
    batch_edit_groups,
    check,
    inventory_rows,
    dataset_problem,
    plan_item_deletes,
    structure_set_from_dataset,
    write_edit_sheet,
    write_findings,
)

RT_STRUCT_STORAGE = "1.2.840.10008.5.1.4.1.1.481.3"
FOR_UID = "1.2.3.9"
S1, S2, S3 = "1.2.3.101", "1.2.3.102", "1.2.3.103"
MULTI, UNKNOWN = "1.2.3.104", "1.2.3.105"


def roi(number, name):
    item = Dataset()
    item.ROINumber = number
    item.ReferencedFrameOfReferenceUID = FOR_UID
    item.ROIName = name
    item.ROIGenerationAlgorithm = "MANUAL"
    return item


def for_only():
    """The item shape the old StructFixer ROI-FOR loop created."""
    item = Dataset()
    item.ReferencedFrameOfReferenceUID = FOR_UID
    return item


def contour(z, geometric_type="CLOSED_PLANAR"):
    item = Dataset()
    item.ContourGeometricType = geometric_type
    item.NumberOfContourPoints = 3
    item.ContourData = [0, 0, z, 1, 0, z, 0, 1, z]
    return item


def roi_contour(number, *contours):
    item = Dataset()
    if number is not None:
        item.ReferencedROINumber = number
    item.ContourSequence = Sequence(list(contours))
    return item


def observation(observation_number, number):
    item = Dataset()
    item.ObservationNumber = observation_number
    if number is not None:
        item.ReferencedROINumber = number
    item.RTROIInterpretedType = "GTV"
    return item


def frame_of_reference(uid):
    item = Dataset()
    item.FrameOfReferenceUID = uid
    return item


def rtstruct(*items, contours=None, observations=None, fors=(FOR_UID,),
             series="1.2.3.100", sop="1.2.3.200"):
    ds = Dataset()
    ds.SOPClassUID = RT_STRUCT_STORAGE
    ds.SOPInstanceUID = sop
    ds.SeriesInstanceUID = series
    ds.Modality = "RTSTRUCT"
    if fors is not None:
        ds.ReferencedFrameOfReferenceSequence = Sequence(
            [frame_of_reference(uid) for uid in fors])
    if items:
        ds.StructureSetROISequence = Sequence(list(items))
    if contours is not None:
        ds.ROIContourSequence = Sequence(list(contours))
    if observations is not None:
        ds.RTROIObservationsSequence = Sequence(list(observations))
    return ds


def round_trip(ds):
    """Write a dataset to bytes and read it back, as it would come off disk."""
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    buf.seek(0)
    return dcmread(buf)


def findings_for(ds, file_id=1):
    return check(structure_set_from_dataset(ds, file_id=file_id))


def apply_item_deletes(items, tags):
    """Apply delete_tag item edits the way Posda does: splice, in input order."""
    items = list(items)
    for tag in tags:
        index = int(re.fullmatch(r"\(3006,0020\)\[(\d+)\]", tag).group(1))
        items.pop(index)
    return items


SEQUENCE_KEYWORDS = {
    "(3006,0020)": "StructureSetROISequence",
    "(3006,0039)": "ROIContourSequence",
    "(3006,0080)": "RTROIObservationsSequence",
}


def apply_to_dataset(ds, tags):
    """Apply delete tags to a dataset in order, as Posda would: an item when
    the tag ends in [n], otherwise the whole sequence."""
    for tag in tags:
        sequence, index = re.fullmatch(r"(\(\w{4},\w{4}\))(?:\[(\d+)\])?", tag).groups()
        if index is None:
            del ds[SEQUENCE_KEYWORDS[sequence]]
        else:
            del ds[SEQUENCE_KEYWORDS[sequence]].value[int(index)]


# ----------------------------------------------------------------------
# Detection
# ----------------------------------------------------------------------

def test_clean_file_has_no_findings():
    assert findings_for(rtstruct(roi(1, "GTVp"), roi(2, "GTVn"))) == []


def test_for_only_items_are_deletable():
    ds = rtstruct(roi(18, "GTVn"), roi(10, "GTVp"), for_only(), for_only(), for_only())
    findings = findings_for(ds)
    assert [f.item_index for f in findings] == [2, 3, 4]
    assert {f.action for f in findings} == {DELETE}
    assert {f.sequence for f in findings} == {"(3006,0020)"}
    assert findings[0].location == "(3006,0020)[2]"
    assert "only Referenced Frame of Reference UID" in findings[0].detail


def test_empty_item_is_deletable():
    findings = findings_for(rtstruct(roi(1, "GTVp"), Dataset()))
    assert len(findings) == 1
    assert findings[0].action == DELETE
    assert findings[0].item_index == 1
    assert findings[0].detail == "empty item"


def test_item_with_other_elements_is_report_only():
    damaged = Dataset()
    damaged.ReferencedFrameOfReferenceUID = FOR_UID
    damaged.ROIName = "GTVp"
    findings = findings_for(rtstruct(roi(1, "GTVn"), damaged))
    assert len(findings) == 1
    assert findings[0].action == REPORT
    assert findings[0].item_index is None
    assert "'GTVp'" in findings[0].detail
    assert "(3006,0026)" in findings[0].detail


def test_empty_roi_number_element_is_report_only():
    item = for_only()
    item.ROINumber = None
    findings = findings_for(rtstruct(roi(1, "GTVp"), item))
    assert len(findings) == 1
    assert findings[0].action == REPORT


def test_empty_items_survive_a_round_trip():
    ds = round_trip(rtstruct(roi(1, "GTVp"), Dataset(), for_only()))
    findings = findings_for(ds)
    assert [(f.item_index, f.action) for f in findings] == [(1, DELETE), (2, DELETE)]


def test_findings_carry_file_and_series_identity():
    ds = rtstruct(roi(1, "GTVp"), for_only(), series="9.9.9", sop="8.8.8")
    (finding,) = findings_for(ds, file_id=42)
    assert (finding.file_id, finding.series_instance_uid, finding.sop_instance_uid) == \
        (42, "9.9.9", "8.8.8")


def test_missing_sequences_are_conformant():
    """Every sequence the rules read is Type 3 in PS3.3."""
    for ds in (rtstruct(fors=None), rtstruct(), rtstruct(roi(1, "a"))):
        assert findings_for(ds) == []


def test_empty_sequences_are_deleted_whole():
    ds = rtstruct(roi(1, "a"), contours=[], observations=[])
    findings = findings_for(round_trip(ds))
    assert [(f.rule, f.location, f.action) for f in findings] == [
        ("empty_sequence", "(3006,0039)", DELETE),
        ("empty_sequence", "(3006,0080)", DELETE),
    ]
    (tags, _), = plan_item_deletes(findings, {"1.2.3.100": 1})[0]
    assert tags == ("(3006,0039)", "(3006,0080)")
    apply_to_dataset(ds, tags)
    assert "ROIContourSequence" not in ds and "RTROIObservationsSequence" not in ds
    assert findings_for(ds) == []


def test_deleting_every_item_deletes_the_sequence():
    """An observation sequence holding only orphans must go, not be left empty."""
    ds = rtstruct(roi(18, "GTVn"),
                  contours=[roi_contour(18, contour(1), contour(2)),
                            roi_contour(11, contour(1)), roi_contour(12, contour(2))],
                  observations=[observation(1, 11), observation(2, 12)])
    (tags, _), = plan_item_deletes(findings_for(ds), {"1.2.3.100": 1})[0]
    assert tags == ("(3006,0039)[2]", "(3006,0039)[1]", "(3006,0080)")
    apply_to_dataset(ds, tags)
    assert "RTROIObservationsSequence" not in ds
    assert [i.ReferencedROINumber for i in ds.ROIContourSequence] == [18]
    assert findings_for(ds) == []


def test_duplicate_roi_numbers_are_report_only():
    ds = rtstruct(roi(1, "GTVp"), roi(2, "GTVn"), roi(1, "CTV"))
    (finding,) = findings_for(ds)
    assert (finding.rule, finding.action) == ("duplicate_roi_number", REPORT)
    assert finding.location == "(3006,0020)[0], (3006,0020)[2]"
    assert "'GTVp', 'CTV'" in finding.detail


def test_roi_numbers_compare_as_integers():
    ds = rtstruct(roi(1, "a"), roi(1, "b"))
    ds.StructureSetROISequence[1].ROINumber = "01"
    (finding,) = findings_for(round_trip(ds))
    assert finding.rule == "duplicate_roi_number"


# ----------------------------------------------------------------------
# References to undeclared ROIs
# ----------------------------------------------------------------------

def merged_rtstruct():
    """ROIs 11 and 12 merged into ROI 18; their contour items and observations left behind."""
    return rtstruct(
        roi(18, "GTVn"), roi(10, "GTVp"),
        contours=[roi_contour(18, contour(1), contour(2), contour(3)),
                  roi_contour(10, contour(9)),
                  roi_contour(11, contour(1), contour(2)),
                  roi_contour(12, contour(3))],
        observations=[observation(1, 18), observation(2, 10),
                      observation(3, 11), observation(4, 12)],
    )


def test_matching_references_have_no_findings():
    ds = rtstruct(roi(1, "a"), contours=[roi_contour(1, contour(1))],
                  observations=[observation(1, 1)])
    assert findings_for(ds) == []


def test_redundant_contour_items_and_their_observations_are_deletable():
    findings = findings_for(merged_rtstruct())
    assert [(f.location, f.action) for f in findings] == [
        ("(3006,0039)[2]", DELETE), ("(3006,0039)[3]", DELETE),
        ("(3006,0080)[2]", DELETE), ("(3006,0080)[3]", DELETE),
    ]
    assert "ROI Number 11" in findings[0].detail
    assert "also in declared ROI 18" in findings[0].detail


def test_unique_contours_are_report_only_and_keep_the_observation():
    ds = rtstruct(roi(1, "a"),
                  contours=[roi_contour(1, contour(1)), roi_contour(7, contour(1), contour(5))],
                  observations=[observation(1, 1), observation(2, 7)])
    findings = findings_for(ds)
    assert [(f.location, f.action) for f in findings] == [
        ("(3006,0039)[1]", REPORT), ("(3006,0080)[1]", REPORT),
    ]
    assert "1 of 2 contour(s)" in findings[0].detail


def test_same_points_different_geometric_type_is_unique():
    ds = rtstruct(roi(1, "a"),
                  contours=[roi_contour(1, contour(1)), roi_contour(7, contour(1, "OPEN_PLANAR"))])
    (finding,) = findings_for(ds)
    assert finding.action == REPORT


def test_contour_item_with_no_contours_is_deletable():
    ds = rtstruct(roi(1, "a"), contours=[roi_contour(1, contour(1)), roi_contour(7)])
    (finding,) = findings_for(ds)
    assert finding.action == DELETE and "no contours" in finding.detail


def test_observation_with_no_contour_item_is_deletable():
    ds = rtstruct(roi(1, "a"), observations=[observation(1, 1), observation(2, 7)])
    (finding,) = findings_for(ds)
    assert (finding.location, finding.action) == ("(3006,0080)[1]", DELETE)


def test_missing_referenced_roi_number_is_report_only():
    ds = rtstruct(roi(1, "a"), contours=[roi_contour(None, contour(1))],
                  observations=[observation(1, None)])
    assert {(f.rule, f.action) for f in findings_for(ds)} == {
        ("roi_contour_without_referenced_roi_number", REPORT),
        ("observation_without_referenced_roi_number", REPORT),
    }


def test_reference_to_an_roi_item_without_roi_number_is_undeclared():
    ds = rtstruct(roi(1, "a"), for_only(), contours=[roi_contour(1, contour(1)), roi_contour(2)])
    assert [(f.location, f.action) for f in findings_for(ds)] == [
        ("(3006,0020)[1]", DELETE), ("(3006,0039)[1]", DELETE),
    ]


def test_contours_match_after_a_round_trip():
    findings = findings_for(round_trip(merged_rtstruct()))
    assert [f.action for f in findings] == [DELETE] * 4


def test_applying_the_plan_across_sequences_leaves_a_clean_file():
    ds = merged_rtstruct()
    ds.StructureSetROISequence.append(for_only())
    (tags, _), = plan_item_deletes(findings_for(ds), {"1.2.3.100": 1})[0]
    assert tags == ("(3006,0020)[2]",
                    "(3006,0039)[3]", "(3006,0039)[2]",
                    "(3006,0080)[3]", "(3006,0080)[2]")
    apply_to_dataset(ds, tags)
    assert findings_for(ds) == []
    assert [i.ReferencedROINumber for i in ds.ROIContourSequence] == [18, 10]
    assert [i.ReferencedROINumber for i in ds.RTROIObservationsSequence] == [18, 10]


# ----------------------------------------------------------------------
# Related ROIs, observation numbers, frames of reference, geometric types
# ----------------------------------------------------------------------

def related(number):
    item = Dataset()
    item.ReferencedROINumber = number
    item.RTROIRelationship = "ENCLOSED"
    return item


def test_related_roi_must_be_declared():
    obs = observation(1, 1)
    obs.RTRelatedROISequence = Sequence([related(2), related(9)])
    ds = rtstruct(roi(1, "CTV"), roi(2, "PTV"), observations=[obs])
    (finding,) = findings_for(ds)
    assert (finding.rule, finding.action) == ("related_roi_not_declared", REPORT)
    assert finding.location == "(3006,0080)[0](3006,0030)[1]"


def test_related_rois_of_an_undeclared_observation_are_not_reported_twice():
    obs = observation(1, 7)
    obs.RTRelatedROISequence = Sequence([related(9)])
    ds = rtstruct(roi(1, "a"), observations=[obs])
    assert [f.rule for f in findings_for(ds)] == ["observation_for_undeclared_roi"]


def test_observation_numbers_must_be_present_and_unique():
    no_number = observation(1, 1)
    del no_number.ObservationNumber
    ds = rtstruct(roi(1, "a"), roi(2, "b"),
                  observations=[no_number, observation(5, 1), observation(5, 2)])
    assert [(f.rule, f.location) for f in findings_for(ds)] == [
        ("observation_without_observation_number", "(3006,0080)[0]"),
        ("duplicate_observation_number", "(3006,0080)[1], (3006,0080)[2]"),
    ]


def test_roi_frame_of_reference_must_be_listed():
    other = roi(2, "b")
    other.ReferencedFrameOfReferenceUID = "1.2.3.8"
    for ds in (rtstruct(roi(1, "a"), other), rtstruct(roi(1, "a"), other, fors=None)):
        rules = [(f.rule, f.location) for f in findings_for(ds)]
        assert ("roi_frame_of_reference_not_listed", "(3006,0020)[1]") in rules


def test_roi_without_frame_of_reference():
    item = roi(1, "a")
    del item.ReferencedFrameOfReferenceUID
    (finding,) = findings_for(rtstruct(item))
    assert finding.rule == "roi_without_frame_of_reference"


def test_frame_of_reference_listed_once():
    (finding,) = findings_for(rtstruct(roi(1, "a"), fors=(FOR_UID, FOR_UID)))
    assert finding.rule == "frame_of_reference_listed_more_than_once"
    assert finding.location == "(3006,0010)[0], (3006,0010)[1]"


def test_closedplanar_xor_cannot_mix_with_other_types():
    ds = rtstruct(roi(1, "a"), contours=[
        roi_contour(1, contour(1, "CLOSEDPLANAR_XOR"), contour(2, "CLOSED_PLANAR"))])
    (finding,) = findings_for(ds)
    assert finding.rule == "closedplanar_xor_mixed_with_other_types"
    assert "CLOSED_PLANAR" in finding.detail


def test_other_geometric_type_mixes_are_conformant():
    ds = rtstruct(roi(1, "a"), roi(2, "b"), contours=[
        roi_contour(1, contour(1), contour(2, "POINT")),
        roi_contour(2, contour(3, "CLOSEDPLANAR_XOR"), contour(4, "CLOSEDPLANAR_XOR"))])
    assert findings_for(ds) == []


def test_several_contour_items_for_one_roi_are_conformant():
    ds = rtstruct(roi(1, "a"), contours=[roi_contour(1, contour(1)), roi_contour(1, contour(2))])
    assert findings_for(ds) == []


# ----------------------------------------------------------------------
# Trusting what was read
# ----------------------------------------------------------------------

def test_expected_rtstruct_has_no_problem():
    assert dataset_problem(rtstruct(roi(1, "a"), sop="1.2.3.200"), "1.2.3.200") is None


def test_wrong_sop_class_is_a_problem():
    ds = rtstruct(roi(1, "a"))
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    assert "not an RT Structure Set" in dataset_problem(ds)


def test_mismatched_sop_instance_is_a_problem():
    problem = dataset_problem(rtstruct(roi(1, "a"), sop="1.2.3.200"), "1.2.3.999")
    assert "does not match" in problem


def test_non_dicom_response_is_never_treated_as_clean():
    """An HTML/JSON body forced through dcmread must not look like a clean RTSTRUCT."""
    for body in (b"<!doctype html><html><body>Login</body></html>",
                 b'{"detail": "Not Found"}', b""):
        try:
            ds = dcmread(io.BytesIO(body), force=True)
        except Exception:
            continue  # the script records a read error as file_not_checked
        assert dataset_problem(ds, "1.2.3.200") is not None


# ----------------------------------------------------------------------
# Edit planning
# ----------------------------------------------------------------------

def test_deletes_are_ordered_highest_index_first():
    ds = rtstruct(roi(1, "a"), roi(2, "b"), for_only(), for_only(), for_only(), for_only())
    groups, skipped = plan_item_deletes(findings_for(ds), {"1.2.3.100": 1})
    assert skipped == []
    assert groups == [(("(3006,0020)[5]", "(3006,0020)[4]",
                        "(3006,0020)[3]", "(3006,0020)[2]"), ["1.2.3.100"])]


def test_applying_the_plan_leaves_only_real_rois():
    items = [roi(18, "GTVn"), roi(10, "GTVp")] + [for_only() for _ in range(7)]
    ds = rtstruct(*items)
    (tags, _), = plan_item_deletes(findings_for(ds), {"1.2.3.100": 1})[0]
    remaining = apply_item_deletes(ds.StructureSetROISequence, tags)
    assert [item.ROINumber for item in remaining] == [18, 10]


def test_ascending_order_would_have_been_wrong():
    """Guards the reason for descending order: splice renumbers later items."""
    items = [roi(1, "a"), roi(2, "b")] + [for_only() for _ in range(3)]
    ascending = ["(3006,0020)[2]", "(3006,0020)[3]", "(3006,0020)[4]"]
    try:
        apply_item_deletes(items, ascending)
    except IndexError:
        pass
    else:
        raise AssertionError("ascending deletes should run past the end")


def test_series_with_identical_deletes_are_grouped():
    one = findings_for(rtstruct(roi(1, "a"), for_only(), series=S1))
    two = findings_for(rtstruct(roi(1, "a"), for_only(), series=S2))
    three = findings_for(rtstruct(roi(1, "a"), roi(2, "b"), for_only(), series=S3))
    groups, _ = plan_item_deletes(one + two + three, {S1: 1, S2: 1, S3: 1})
    assert groups == [
        (("(3006,0020)[1]",), [S1, S2]),
        (("(3006,0020)[2]",), [S3]),
    ]


def test_multi_file_and_unknown_series_are_skipped():
    findings = (findings_for(rtstruct(roi(1, "a"), for_only(), series=MULTI))
                + findings_for(rtstruct(roi(1, "a"), for_only(), series=UNKNOWN)))
    groups, skipped = plan_item_deletes(findings, {MULTI: 2})
    assert groups == []
    assert [s for s, _ in skipped] == [MULTI, UNKNOWN]
    assert "2 files" in dict(skipped)[MULTI]


def test_report_findings_produce_no_edits():
    damaged = Dataset()
    damaged.ROIName = "GTVp"
    groups, skipped = plan_item_deletes(findings_for(rtstruct(roi(1, "a"), damaged)),
                                        {"1.2.3.100": 1})
    assert groups == [] and skipped == []


# ----------------------------------------------------------------------
# Spreadsheets
# ----------------------------------------------------------------------

def test_edit_sheet_layout():
    groups = [(("(3006,0020)[1]",), [S1, S2]),
              (("(3006,0020)[3]", "(3006,0020)[2]"), [S3])]
    buf = io.StringIO()
    write_edit_sheet(buf, groups, {S1: 1, S2: 1, S3: 1},
                     "Delete empty Structure Set ROI items", "someone", "7")
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert rows[0] == EDIT_SHEET_HEADER
    assert rows[1] == [S1, "1", "", "", "", "", "BackgroundEditTp",
                       "Delete empty Structure Set ROI items", "someone", "7"]
    assert rows[2] == [S2, "1", "", "", "", "", "", "", "", ""]
    assert rows[3] == ["", "", "delete_tag", "<(3006,0020)[1]>", "<>", "", "", "", "", ""]
    assert rows[4][0] == S3 and rows[4][6] == ""
    assert [r[3] for r in rows[5:]] == ["<(3006,0020)[3]>", "<(3006,0020)[2]>"]


def test_findings_sheet():
    buf = io.StringIO()
    write_findings(buf, findings_for(rtstruct(roi(1, "a"), for_only()), file_id=5))
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert rows[0][:5] == ["file_id", "series_instance_uid", "sop_instance_uid", "rule", "action"]
    assert rows[1][0] == "5" and rows[1][4] == DELETE and rows[1][5] == "(3006,0020)[1]"


# ----------------------------------------------------------------------
# Inventory
# ----------------------------------------------------------------------

def inventory_for(ds):
    ss = structure_set_from_dataset(ds, file_id=1)
    rows = [dict(zip(INVENTORY_HEADER, r)) for r in inventory_rows(ss, check(ss))]
    return {r["roi_number"]: r for r in rows}, rows


def test_inventory_describes_what_is_in_place():
    obs = observation(1, 1)
    obs.RTRelatedROISequence = Sequence([related(2)])
    by_number, rows = inventory_for(rtstruct(
        roi(1, "CTV"), roi(2, "PTV"),
        contours=[roi_contour(1, contour(1), contour(2, "POINT")), roi_contour(2, contour(3))],
        observations=[obs, observation(2, 2)]))
    assert len(rows) == 2
    ctv = by_number[1]
    assert (ctv["declared"], ctv["roi_item"], ctv["roi_name"], ctv["for_listed"]) ==         ("yes", "(3006,0020)[0]", "CTV", "yes")
    assert (ctv["contour_items"], ctv["contours"], ctv["geometric_types"]) ==         (1, 2, "CLOSED_PLANAR, POINT")
    assert (ctv["observations"], ctv["interpreted_type"], ctv["related_rois"]) == ("1", "GTV", "2")
    assert {r["status"] for r in rows} == {"ok"}


def test_inventory_lists_undeclared_rois_with_their_findings():
    by_number, rows = inventory_for(merged_rtstruct())
    assert [r["roi_number"] for r in rows] == [18, 10, 11, 12]
    assert by_number[18]["status"] == "ok" and by_number[18]["contours"] == 3
    orphan = by_number[11]
    assert (orphan["declared"], orphan["roi_item"], orphan["contours"]) == ("no", None, 2)
    assert orphan["status"] == "observation_for_undeclared_roi, roi_contour_for_undeclared_roi"


def test_inventory_status_matches_only_the_roi_s_own_items():
    """(3006,0080)[1] must not pick up a finding at (3006,0080)[10]."""
    rois = [roi(n, str(n)) for n in range(1, 12)]
    observations = [observation(n, n) for n in range(1, 11)] + [observation(11, 99)]
    by_number, _ = inventory_for(rtstruct(*rois, observations=observations))
    assert by_number[2]["status"] == "ok"
    assert by_number[99]["status"] == "observation_for_undeclared_roi"


def test_inventory_rows_for_rule_with_multiple_locations():
    by_number, rows = inventory_for(rtstruct(roi(1, "a"), roi(2, "b"), roi(1, "c")))
    assert [r["status"] for r in rows] == ["duplicate_roi_number", "ok", "duplicate_roi_number"]


def test_inventory_item_without_roi_number():
    _, rows = inventory_for(rtstruct(roi(1, "a"), for_only()))
    assert (rows[1]["roi_number"], rows[1]["declared"], rows[1]["status"]) ==         (None, "no", "roi_item_without_roi_number")


# ----------------------------------------------------------------------
# Batching
# ----------------------------------------------------------------------

def test_batches_keep_groups_whole():
    groups = [(("t1",), ["a", "b"]), (("t2", "t3"), ["c"]), (("t4",), ["d", "e"])]
    assert batch_edit_groups(groups, 6) == [
        [(("t1",), ["a", "b"]), (("t2", "t3"), ["c"])],
        [(("t4",), ["d", "e"])],
    ]


def test_oversized_group_is_split_by_series_with_its_deletes_repeated():
    batches = batch_edit_groups([(("t1", "t2"), list("abcdefg"))], 5)
    assert batches == [[(("t1", "t2"), list("abc"))], [(("t1", "t2"), list("def"))],
                       [(("t1", "t2"), ["g"])]]
    assert all(sum(len(s) + len(t) for t, s in b) <= 5 for b in batches)


def test_every_edit_sheet_part_carries_the_operation():
    batches = batch_edit_groups([(("(3006,0080)",), [S1, S2]), (("(3006,0039)[0]",), [S3])], 3)
    for batch in batches:
        buf = io.StringIO()
        write_edit_sheet(buf, batch, {S1: 1, S2: 1, S3: 1}, "d", "n", "1")
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        assert rows[1][6] == "BackgroundEditTp"
