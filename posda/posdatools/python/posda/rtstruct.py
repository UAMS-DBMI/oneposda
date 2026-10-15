"""Internal-consistency checks for RT Structure Set (RTSTRUCT) files.

A small model of one structure set is built from its DICOM dataset, and rules
run over that model. Each rule yields Findings. A finding that can be fixed by
deleting a sequence item carries that item's location, and write_edit_sheet()
turns those into a BackgroundEditTp spreadsheet.

The model is read from the file, not from the posda_files ROI tables. Ingest
drops exactly the malformed items these rules look for -- a Structure Set ROI
item with no ROI Number is skipped without an error -- so a check built on the
DB would never see them.

Conformance basis: each rule cites the DICOM PS3.3 requirement it enforces
(checked against the 2026d edition). Every sequence these rules read --
Structure Set ROI, Referenced Frame of Reference, ROI Contour, RT ROI
Observations, RT Related ROI -- is Type 3 there, so a missing sequence, or a
declared ROI with no contour item or observation, is conformant and not a
finding. Considered and deliberately not rules:
  - Several ROI Contour items for one ROI: the standard doesn't address it.
  - Mixed Contour Geometric Types in one ROI: only prohibited when one of
    them is CLOSEDPLANAR_XOR (see closedplanar_xor_mixed_with_other_types).
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field

from pydicom.tag import Tag

RT_STRUCTURE_SET_STORAGE = "1.2.840.10008.5.1.4.1.1.481.3"
STRUCTURE_SET_ROI_SEQUENCE = "(3006,0020)"
REFERENCED_FRAME_OF_REFERENCE_SEQUENCE = "(3006,0010)"
ROI_CONTOUR_SEQUENCE = "(3006,0039)"
RT_ROI_OBSERVATIONS_SEQUENCE = "(3006,0080)"
RT_RELATED_ROI_SEQUENCE = "(3006,0030)"

CLOSEDPLANAR_XOR = "CLOSEDPLANAR_XOR"

FRAME_OF_REFERENCE_UID = Tag(0x0020, 0x0052)
ROI_NUMBER = Tag(0x3006, 0x0022)
REFERENCED_FRAME_OF_REFERENCE_UID = Tag(0x3006, 0x0024)
ROI_NAME = Tag(0x3006, 0x0026)
CONTOUR_GEOMETRIC_TYPE = Tag(0x3006, 0x0042)
REFERENCED_ROI_NUMBER = Tag(0x3006, 0x0084)
OBSERVATION_NUMBER = Tag(0x3006, 0x0082)

DELETE = "delete"
REPORT = "report"

FINDINGS_HEADER = [
    "file_id", "series_instance_uid", "sop_instance_uid",
    "rule", "action", "location", "detail",
]

# Same layout as LinkageChecker.create_edit_skeleton(). BackgroundEditTp reads
# the columns by name, so num_files is informational only.
EDIT_SHEET_HEADER = [
    "series_instance_uid", "num_files", "op", "tag", "val1", "val2",
    "Operation", "edit_description", "notify", "activity_id",
]


@dataclass(frozen=True)
class RoiItem:
    """One item of the Structure Set ROI Sequence (3006,0020)."""
    index: int
    tags: frozenset
    roi_number: int | str | None
    roi_name: str | None
    referenced_for_uid: str | None = None


@dataclass(frozen=True)
class RoiContourItem:
    """One item of the ROI Contour Sequence (3006,0039)."""
    index: int
    referenced_roi_number: int | str | None
    contours: tuple   # one (geometric type, points) per contour


@dataclass(frozen=True)
class ObservationItem:
    """One item of the RT ROI Observations Sequence (3006,0080)."""
    index: int
    referenced_roi_number: int | str | None
    observation_number: int | str | None = None
    related_roi_numbers: tuple = ()   # Referenced ROI Number per RT Related ROI item


@dataclass
class StructureSet:
    file_id: int | None
    series_instance_uid: str | None
    sop_instance_uid: str | None
    roi_items: list[RoiItem]
    roi_contour_items: list[RoiContourItem] = field(default_factory=list)
    observation_items: list[ObservationItem] = field(default_factory=list)
    referenced_for_uids: list = field(default_factory=list)  # one per (3006,0010) item


@dataclass(frozen=True)
class Finding:
    file_id: int | None
    series_instance_uid: str | None
    sop_instance_uid: str | None
    rule: str
    action: str             # DELETE or REPORT
    location: str           # e.g. "(3006,0020)[2]"
    detail: str
    sequence: str | None = None    # set for DELETE: the sequence holding the item
    item_index: int | None = None  # set for DELETE: the item's index in it

    def to_row(self):
        return [self.file_id, self.series_instance_uid, self.sop_instance_uid,
                self.rule, self.action, self.location, self.detail]


def _value(item, tag):
    """Return an element's value as a stripped string, or None if absent/empty."""
    if tag not in item:
        return None
    value = item[tag].value
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _number(item, tag):
    """Return an ROI Number as an int (so "011" matches 11), the raw string if
    it isn't an integer, or None if absent/empty."""
    value = _value(item, tag)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _contour_key(contour):
    """Identify a contour by its geometric type and points."""
    data = contour.get("ContourData")
    if data is None:
        values = []
    else:
        try:
            values = list(data)
        except TypeError:  # a single value
            values = [data]
    try:
        points = tuple(float(v) for v in values)
    except (TypeError, ValueError):
        points = tuple(str(v).strip() for v in values)
    return (_value(contour, CONTOUR_GEOMETRIC_TYPE), points)


def dataset_problem(ds, expected_sop_instance_uid=None):
    """Return why ds can't be trusted as the expected RTSTRUCT, or None if it can.

    Datasets are read with force=True, so a response that isn't DICOM at all
    can still come back as a (mostly empty) dataset. Without this check such a
    file would have no ROI items and pass every rule as clean.
    """
    sop_class = ds.get("SOPClassUID")
    if sop_class != RT_STRUCTURE_SET_STORAGE:
        return f"not an RT Structure Set (SOP Class UID {sop_class!r})"
    sop_instance = ds.get("SOPInstanceUID")
    if expected_sop_instance_uid and sop_instance != expected_sop_instance_uid:
        return (f"SOP Instance UID {sop_instance!r} does not match the "
                f"expected {expected_sop_instance_uid!r}")
    return None


def structure_set_from_dataset(ds, file_id=None, series_instance_uid=None):
    """Build a StructureSet model from a pydicom Dataset."""
    if series_instance_uid is None:
        series_instance_uid = ds.get("SeriesInstanceUID")
    roi_items = []
    for index, item in enumerate(ds.get("StructureSetROISequence") or []):
        roi_items.append(RoiItem(
            index=index,
            tags=frozenset(elem.tag for elem in item),
            roi_number=_number(item, ROI_NUMBER),
            roi_name=_value(item, ROI_NAME),
            referenced_for_uid=_value(item, REFERENCED_FRAME_OF_REFERENCE_UID),
        ))
    roi_contour_items = [
        RoiContourItem(
            index=index,
            referenced_roi_number=_number(item, REFERENCED_ROI_NUMBER),
            contours=tuple(_contour_key(c) for c in item.get("ContourSequence") or []),
        )
        for index, item in enumerate(ds.get("ROIContourSequence") or [])
    ]
    observation_items = [
        ObservationItem(
            index=index,
            referenced_roi_number=_number(item, REFERENCED_ROI_NUMBER),
            observation_number=_number(item, OBSERVATION_NUMBER),
            related_roi_numbers=tuple(_number(related, REFERENCED_ROI_NUMBER)
                                      for related in item.get("RTRelatedROISequence") or []),
        )
        for index, item in enumerate(ds.get("RTROIObservationsSequence") or [])
    ]
    return StructureSet(
        file_id=file_id,
        series_instance_uid=series_instance_uid,
        sop_instance_uid=ds.get("SOPInstanceUID"),
        roi_items=roi_items,
        roi_contour_items=roi_contour_items,
        observation_items=observation_items,
        referenced_for_uids=[_value(item, FRAME_OF_REFERENCE_UID)
                             for item in ds.get("ReferencedFrameOfReferenceSequence") or []],
    )


# ----------------------------------------------------------------------
# Rules -- each takes a StructureSet and yields Findings
# ----------------------------------------------------------------------

def roi_items_without_roi_number(ss):
    """Structure Set ROI items that have no ROI Number (3006,0022).

    PS3.3 C.8.8.5: ROI Number is Type 1 in every Structure Set ROI item.

    Every ROI reference in an RT Structure Set resolves by ROI Number, so an
    item without one cannot be referenced. An item that is empty, or holds
    only a Referenced Frame of Reference UID (the shape StructFixer used to
    create), is safe to delete. Anything else may be a damaged real ROI, so it
    is reported but never deleted automatically.
    """
    deletable = {REFERENCED_FRAME_OF_REFERENCE_UID}
    for item in ss.roi_items:
        if item.roi_number is not None:
            continue
        location = f"{STRUCTURE_SET_ROI_SEQUENCE}[{item.index}]"
        if item.tags <= deletable:
            detail = ("empty item" if not item.tags
                      else "item holds only Referenced Frame of Reference UID")
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="roi_item_without_roi_number", action=DELETE,
                location=location, detail=detail,
                sequence=STRUCTURE_SET_ROI_SEQUENCE, item_index=item.index,
            )
        else:
            present = ", ".join(f"({t.group:04X},{t.element:04X})" for t in sorted(item.tags))
            name = f" (ROI Name {item.roi_name!r})" if item.roi_name else ""
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="roi_item_without_roi_number", action=REPORT,
                location=location,
                detail=f"no ROI Number but holds other elements{name}: {present}",
            )


def duplicate_roi_numbers(ss):
    """ROI Numbers declared by more than one Structure Set ROI item.

    PS3.3 C.8.8.5: "The Value of ROI Number (3006,0022) shall be unique within
    the Structure Set in which it is created." With a duplicate, a reference to
    that number can't be resolved, so there's no safe edit.
    """
    items_by_number = defaultdict(list)
    for item in ss.roi_items:
        if item.roi_number is not None:
            items_by_number[item.roi_number].append(item)
    for number, items in items_by_number.items():
        if len(items) < 2:
            continue
        names = ", ".join(repr(item.roi_name) for item in items)
        yield Finding(
            ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
            rule="duplicate_roi_number", action=REPORT,
            location=", ".join(f"{STRUCTURE_SET_ROI_SEQUENCE}[{item.index}]" for item in items),
            detail=f"ROI Number {number} declared by {len(items)} items (ROI Names {names})",
        )


def undeclared_roi_references(ss):
    """ROI Contour items and RT ROI Observations whose Referenced ROI Number
    (3006,0084) is not declared in the Structure Set ROI Sequence.

    PS3.3 C.8.8.6 and C.8.8.8: Referenced ROI Number is Type 1 in both, and
    "Uniquely identifies the referenced ROI described in the Structure Set ROI
    Sequence (3006,0020)."

    A contour item is safe to delete when it has no contours, or when every
    one of its contours (same geometric type and points) is also in a declared
    ROI -- e.g. ROIs merged into another one without removing the originals.
    If any contour exists only there, the ROI's declaration may have been
    dropped by mistake, so the item is reported and never deleted.

    An observation for an undeclared ROI is deleted unless that ROI Number has
    such a unique contour item: its label and interpreted type are what
    restoring the declaration would need.
    """
    declared = {item.roi_number for item in ss.roi_items if item.roi_number is not None}
    declared_contours = defaultdict(set)  # contour key -> declared ROI Numbers holding it
    for item in ss.roi_contour_items:
        if item.referenced_roi_number in declared:
            for contour in item.contours:
                declared_contours[contour].add(item.referenced_roi_number)

    has_unique_contours = set()
    for item in ss.roi_contour_items:
        number = item.referenced_roi_number
        if number in declared:
            continue
        location = f"{ROI_CONTOUR_SEQUENCE}[{item.index}]"
        if number is None:
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="roi_contour_without_referenced_roi_number", action=REPORT,
                location=location, detail="ROI Contour item has no Referenced ROI Number",
            )
            continue
        unique = [c for c in item.contours if c not in declared_contours]
        if unique:
            has_unique_contours.add(number)
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="roi_contour_for_undeclared_roi", action=REPORT,
                location=location,
                detail=(f"references undeclared ROI Number {number}; {len(unique)} of "
                        f"{len(item.contours)} contour(s) are in no declared ROI"),
            )
            continue
        if item.contours:
            owners = sorted({n for c in item.contours for n in declared_contours[c]}, key=str)
            detail = (f"references undeclared ROI Number {number}; all {len(item.contours)} "
                      f"contour(s) also in declared ROI {', '.join(map(str, owners))}")
        else:
            detail = f"references undeclared ROI Number {number}; no contours"
        yield Finding(
            ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
            rule="roi_contour_for_undeclared_roi", action=DELETE,
            location=location, detail=detail,
            sequence=ROI_CONTOUR_SEQUENCE, item_index=item.index,
        )

    for item in ss.observation_items:
        number = item.referenced_roi_number
        if number in declared:
            continue
        location = f"{RT_ROI_OBSERVATIONS_SEQUENCE}[{item.index}]"
        if number is None:
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="observation_without_referenced_roi_number", action=REPORT,
                location=location, detail="RT ROI Observation has no Referenced ROI Number",
            )
        elif number in has_unique_contours:
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="observation_for_undeclared_roi", action=REPORT,
                location=location,
                detail=(f"references undeclared ROI Number {number}, which has contours "
                        f"in no declared ROI"),
            )
        else:
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="observation_for_undeclared_roi", action=DELETE,
                location=location, detail=f"references undeclared ROI Number {number}",
                sequence=RT_ROI_OBSERVATIONS_SEQUENCE, item_index=item.index,
            )


def related_roi_references(ss):
    """RT Related ROI items (3006,0030) whose Referenced ROI Number is missing
    or not declared.

    PS3.3 C.8.8.8: Referenced ROI Number is Type 1 in an RT Related ROI item and
    "Uniquely identifies the related ROI described in the Structure Set ROI
    Sequence (3006,0020)." Observations for an undeclared ROI are skipped:
    undeclared_roi_references already covers the whole item.
    """
    declared = {item.roi_number for item in ss.roi_items if item.roi_number is not None}
    for item in ss.observation_items:
        if item.referenced_roi_number not in declared:
            continue
        for related_index, number in enumerate(item.related_roi_numbers):
            if number in declared:
                continue
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="related_roi_not_declared", action=REPORT,
                location=(f"{RT_ROI_OBSERVATIONS_SEQUENCE}[{item.index}]"
                          f"{RT_RELATED_ROI_SEQUENCE}[{related_index}]"),
                detail=(f"observation for ROI Number {item.referenced_roi_number} relates to "
                        + ("no ROI Number" if number is None
                           else f"undeclared ROI Number {number}")),
            )


def observation_numbers(ss):
    """RT ROI Observations with a missing or duplicate Observation Number.

    PS3.3 C.8.8.8: Observation Number (3006,0082) is Type 1 and "shall be unique
    within the RT ROI Observations Sequence (3006,0080)."
    """
    items_by_number = defaultdict(list)
    for item in ss.observation_items:
        if item.observation_number is None:
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="observation_without_observation_number", action=REPORT,
                location=f"{RT_ROI_OBSERVATIONS_SEQUENCE}[{item.index}]",
                detail="RT ROI Observation has no Observation Number",
            )
        else:
            items_by_number[item.observation_number].append(item)
    for number, items in items_by_number.items():
        if len(items) < 2:
            continue
        yield Finding(
            ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
            rule="duplicate_observation_number", action=REPORT,
            location=", ".join(f"{RT_ROI_OBSERVATIONS_SEQUENCE}[{item.index}]" for item in items),
            detail=f"Observation Number {number} used by {len(items)} observations",
        )


def roi_frames_of_reference(ss):
    """ROI Frames of Reference missing from, or repeated in, the Referenced
    Frame of Reference Sequence (3006,0010).

    PS3.3 C.8.8.5: Referenced Frame of Reference UID (3006,0024) is Type 1 in
    every ROI item. C.8.8.5.1: "each Frame of Reference used to express the
    coordinates of an ROI shall be listed in the Referenced Frame of Reference
    Sequence (3006,0010) once and only once." ROI items without an ROI Number
    are left to roi_items_without_roi_number.
    """
    listed = defaultdict(list)
    for index, uid in enumerate(ss.referenced_for_uids):
        listed[uid].append(index)
    for item in ss.roi_items:
        if item.roi_number is None:
            continue
        location = f"{STRUCTURE_SET_ROI_SEQUENCE}[{item.index}]"
        if item.referenced_for_uid is None:
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="roi_without_frame_of_reference", action=REPORT, location=location,
                detail=f"ROI Number {item.roi_number} has no Referenced Frame of Reference UID",
            )
        elif item.referenced_for_uid not in listed:
            yield Finding(
                ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
                rule="roi_frame_of_reference_not_listed", action=REPORT, location=location,
                detail=(f"ROI Number {item.roi_number}'s Frame of Reference "
                        f"{item.referenced_for_uid} is not in the Referenced Frame of "
                        f"Reference Sequence"),
            )
    for uid, indices in listed.items():
        if len(indices) < 2:
            continue
        yield Finding(
            ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
            rule="frame_of_reference_listed_more_than_once", action=REPORT,
            location=", ".join(f"{REFERENCED_FRAME_OF_REFERENCE_SEQUENCE}[{i}]" for i in indices),
            detail=f"Frame of Reference {uid} is listed {len(indices)} times",
        )


def closedplanar_xor_mixed_with_other_types(ss):
    """Declared ROIs with CLOSEDPLANAR_XOR contours mixed with other types.

    PS3.3 C.8.8.6: "If any of the Contours within an ROI is of Contour
    Geometric Type (3006,0042) CLOSEDPLANAR_XOR, all Contours of that ROI shall
    be of the same type." Other mixes (e.g. CLOSED_PLANAR with POINT) are
    allowed, so they are not findings.
    """
    declared = {item.roi_number for item in ss.roi_items if item.roi_number is not None}
    items_by_roi = defaultdict(list)
    for item in ss.roi_contour_items:
        if item.referenced_roi_number in declared:
            items_by_roi[item.referenced_roi_number].append(item)
    for number, items in items_by_roi.items():
        types = {geometric_type for item in items for geometric_type, _ in item.contours}
        if CLOSEDPLANAR_XOR not in types or len(types) < 2:
            continue
        yield Finding(
            ss.file_id, ss.series_instance_uid, ss.sop_instance_uid,
            rule="closedplanar_xor_mixed_with_other_types", action=REPORT,
            location=", ".join(f"{ROI_CONTOUR_SEQUENCE}[{item.index}]" for item in items),
            detail=(f"ROI Number {number} mixes {CLOSEDPLANAR_XOR} with "
                    f"{', '.join(sorted(str(t) for t in types - {CLOSEDPLANAR_XOR}))}"),
        )


RULES = (
    roi_items_without_roi_number,
    duplicate_roi_numbers,
    roi_frames_of_reference,
    undeclared_roi_references,
    related_roi_references,
    observation_numbers,
    closedplanar_xor_mixed_with_other_types,
)


def check(ss, rules=RULES):
    """Run every rule over one StructureSet and return all findings."""
    return [finding for rule in rules for finding in rule(ss)]


# ----------------------------------------------------------------------
# Edit generation
# ----------------------------------------------------------------------

def plan_item_deletes(findings, files_per_series):
    """Turn DELETE findings into BackgroundEditTp item-delete edits.

    Deleting a sequence item renumbers every item after it, and edits are
    applied in the order given, so each sequence's deletes are ordered from the
    highest index down. BackgroundEditTp applies the same edits to every file
    in a series, so series holding more than one file -- or whose file count
    is unknown -- are skipped.

    Returns (groups, skipped):
      groups  -- list of (tags, series_uids), tags in the order to apply them,
                 series grouped by identical edit lists
      skipped -- list of (series_uid, reason)
    """
    by_series = defaultdict(lambda: defaultdict(set))
    for f in findings:
        if f.action == DELETE:
            by_series[f.series_instance_uid][f.sequence].add(f.item_index)

    by_tags = defaultdict(list)
    skipped = []
    for series_uid in sorted(by_series):
        num_files = files_per_series.get(series_uid)
        if num_files is None:
            skipped.append((series_uid, "file count for series unknown"))
            continue
        if num_files != 1:
            skipped.append((series_uid,
                            f"series holds {num_files} files; item indices are per file"))
            continue
        tags = tuple(
            f"{sequence}[{index}]"
            for sequence in sorted(by_series[series_uid])
            for index in sorted(by_series[series_uid][sequence], reverse=True)
        )
        by_tags[tags].append(series_uid)

    groups = sorted(by_tags.items(), key=lambda kv: (len(kv[0]), kv[0]))
    return groups, skipped


def write_edit_sheet(fh, groups, files_per_series, description, notify, activity_id):
    """Write a BackgroundEditTp spreadsheet for planned item deletes.

    Each group is its series rows followed by its delete_tag rows. Operation,
    description, notify and activity_id go on the first series row only.
    """
    writer = csv.writer(fh, lineterminator="\n")
    writer.writerow(EDIT_SHEET_HEADER)
    first = True
    for tags, series_uids in groups:
        for series_uid in series_uids:
            if first:
                writer.writerow([series_uid, files_per_series.get(series_uid),
                                 None, None, None, None,
                                 "BackgroundEditTp", description, notify, activity_id])
                first = False
            else:
                writer.writerow([series_uid, files_per_series.get(series_uid),
                                 None, None, None, None, None, None, None, None])
        for tag in tags:
            writer.writerow([None, None, "delete_tag", f"<{tag}>", "<>", None,
                             None, None, None, None])


def write_findings(fh, findings):
    writer = csv.writer(fh, lineterminator="\n")
    writer.writerow(FINDINGS_HEADER)
    for f in findings:
        writer.writerow(f.to_row())
