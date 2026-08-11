"""RT Structure Set handlers, ported from ``Posda::DB::Modules``.

``StructureSet``, ``RoiContour`` and ``RtRoiObservations`` run as a group and
communicate through ``hist``:

- ``structure_set_id`` and ``ss_for_by_item`` are produced by StructureSet;
  ``ss_for_by_item`` memoises one ``ss_for`` row per frame-of-reference item
  so repeated references to the same item reuse it.
- ``roi`` maps ROI number to the row StructureSet created. RoiContour and
  RtRoiObservations both resolve their ``ReferencedROINumber`` through it and
  complain if the ROI was never defined.

That shared state is why the three cannot be split across processes, and was
the reason the earlier Perl bridge had to run the whole block in one call.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from posda.ingest import fixes
from posda.ingest.coercions import get_attrs
from posda.ingest.values import ParsedValues

if TYPE_CHECKING:
    from posda.ingest.db import Database

log = logging.getLogger(__name__)


def structure_set(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``StructureSet``."""
    parms = get_attrs(
        values,
        {
            "ss_date": "(3006,0008)",
            "ss_time": "(3006,0009)",
            "ss_label": "(3006,0002)",
            "ss_name": "(3006,0004)",
            "ss_desc": "(3006,0006)",
            "ss_inst_num": "(0020,0013)",
        },
        {"ss_date": "Date", "ss_time": "Timetag"},
        errors,
    )
    ss_id = db.insert_returning(
        "insert into structure_set"
        " (ss_label, ss_description, ss_date, ss_time, ss_name)"
        " values (%s, %s, %s, %s, %s)",
        [
            parms.get("ss_label"),
            parms.get("ss_desc"),
            parms.get("ss_date"),
            parms.get("ss_time"),
            parms.get("ss_name"),
        ],
        "structure_set_id",
    )
    if ss_id is None:
        errors.append("couldn't create structure set row")
        return

    hist["structure_set_id"] = ss_id
    db.execute(
        "insert into file_structure_set"
        " (file_id, structure_set_id, instance_number) values (%s, %s, %s)",
        [file_id, ss_id, parms.get("ss_inst_num")],
    )

    _frame_of_reference_registrations(db, values, hist, errors)
    _referenced_volumes(db, values, hist, errors)
    _rois(db, values, ss_id, hist, errors)


def _create_ss_for(
    db: "Database", hist: dict, for_item: int, for_uid: object
) -> object:
    """Port of ``CreateSsFor``: one ss_for row per frame-of-reference item."""
    by_item = hist.setdefault("ss_for_by_item", {})
    if for_item in by_item:
        return by_item[for_item]
    ss_for_id = db.insert_returning(
        "insert into ss_for (structure_set_id, for_uid) values (%s, %s)",
        [hist.get("structure_set_id"), for_uid],
        "ss_for_id",
    )
    by_item[for_item] = ss_for_id
    return ss_for_id


def _frame_of_reference_registrations(
    db: "Database", values: ParsedValues, hist: dict, errors: list[str]
) -> None:
    matches = values.substitutions("(3006,0010)[<0>](3006,00c0)[<1>](3006,00c2)")
    for for_item, rel_item in matches:
        base = f"(3006,0010)[{for_item}]"
        related = f"{base}(3006,00c0)[{rel_item}]"
        to_for = values.get(f"{base}(0020,0052)")
        ss_for_id = _create_ss_for(db, hist, for_item, to_for)
        parms = get_attrs(
            values,
            {
                "from_for": f"{related}(3006,00c2)",
                "xform_type": f"{related}(3006,00c4)",
                "xform_mtx": f"{related}(3006,00c6)",
                "xform_cmt": f"{related}(3006,00c8)",
            },
            {"xform_mtx": "MultiText"},
            errors,
        )
        db.execute(
            "insert into for_registration"
            " (ss_for_id, from_for_uid, xform_type, xform, xform_comment)"
            " values (%s, %s, %s, %s, %s)",
            [
                ss_for_id,
                parms.get("from_for"),
                parms.get("xform_type"),
                parms.get("xform_mtx"),
                parms.get("xform_cmt"),
            ],
        )


def _referenced_volumes(
    db: "Database", values: ParsedValues, hist: dict, errors: list[str]
) -> None:
    pattern = (
        "(3006,0010)[<0>](3006,0012)[<1>]" "(3006,0014)[<2>](3006,0016)[<3>](0008,1155)"
    )
    for for_item, study_item, series_item, image_item in values.substitutions(pattern):
        base = f"(3006,0010)[{for_item}]"
        study = f"{base}(3006,0012)[{study_item}]"
        series = f"{study}(3006,0014)[{series_item}]"
        image = f"{series}(3006,0016)[{image_item}]"

        to_for = values.get(f"{base}(0020,0052)")
        ss_for_id = _create_ss_for(db, hist, for_item, to_for)
        parms = get_attrs(
            values,
            {
                "study_instance_uid": f"{study}(0008,1155)",
                "series_instance_uid": f"{series}(0020,000e)",
                "sop_class": f"{image}(0008,1150)",
                "sop_instance": f"{image}(0008,1155)",
            },
            {},
            errors,
        )
        missing = next(
            (
                name
                for name in (
                    "study_instance_uid",
                    "series_instance_uid",
                    "sop_class",
                    "sop_instance",
                )
                if parms.get(name) is None
            ),
            None,
        )
        if missing is not None:
            errors.append(f"undefined {missing} in {image}")
            continue

        db.execute(
            "insert into ss_volume"
            " (ss_for_id, study_instance_uid, series_instance_uid, sop_class,"
            "  sop_instance) values (%s, %s, %s, %s, %s)",
            [
                ss_for_id,
                parms.get("study_instance_uid"),
                parms.get("series_instance_uid"),
                parms.get("sop_class"),
                parms.get("sop_instance"),
            ],
        )


def _rois(
    db: "Database",
    values: ParsedValues,
    ss_id: object,
    hist: dict,
    errors: list[str],
) -> None:
    for (roi_item,) in values.substitutions("(3006,0020)[<0>](3006,0022)"):
        base = f"(3006,0020)[{roi_item}]"
        parms = get_attrs(
            values,
            {
                "roi_num": f"{base}(3006,0022)",
                "ref_for": f"{base}(3006,0024)",
                "name": f"{base}(3006,0026)",
                "desc": f"{base}(3006,0028)",
                "vol": f"{base}(3006,002c)",
                "gen_alg": f"{base}(3006,0036)",
                "gen_alg_desc": f"{base}(3006,0038)",
            },
            {},
            errors,
        )
        roi_id = db.insert_returning(
            "insert into roi"
            " (structure_set_id, for_uid, roi_num, roi_name, roi_description,"
            "  roi_volume, gen_alg, gen_desc)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s)",
            [
                ss_id,
                parms.get("ref_for"),
                parms.get("roi_num"),
                parms.get("name"),
                parms.get("desc"),
                parms.get("vol"),
                parms.get("gen_alg"),
                parms.get("gen_alg_desc"),
            ],
            "roi_id",
        )
        if roi_id is None:
            errors.append("couldn't create roi row")
            return
        parms["roi_id"] = roi_id
        # Perl hash keys stringify, so ROI numbers are compared as text on
        # both the storing and the looking-up side.
        hist.setdefault("roi", {})[_key(parms.get("roi_num"))] = parms


def _key(roi_num: object) -> str:
    return "" if roi_num is None else str(roi_num)


def roi_contour(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RoiContour``."""
    rois = hist.get("roi", {})
    for (contour_item,) in values.substitutions("(3006,0039)[<0>](3006,0084)"):
        base = f"(3006,0039)[{contour_item}]"
        ref_roi_num = values.get(f"{base}(3006,0084)")
        if _key(ref_roi_num) not in rois:
            errors.append(
                f"ROI Contour item {contour_item} references "
                f"non-existent ROI {_render(ref_roi_num)}"
            )
            continue
        roi_id = rois[_key(ref_roi_num)]["roi_id"]

        colour = values.get(f"{base}(3006,002a)")
        if isinstance(colour, list):
            # The Perl interpolates exactly three components rather than
            # joining the whole list.
            joined = "\\".join(_render(c) for c in colour[:3])
            db.execute(
                "update roi set roi_color = %s where roi_id = %s",
                [joined, roi_id],
            )

        for (item,) in values.substitutions(f"{base}(3006,0040)[<0>]"):
            _contour(db, values, f"{base}(3006,0040)[{item}]", roi_id, errors)


def _contour(
    db: "Database",
    values: ParsedValues,
    base: str,
    roi_id: object,
    errors: list[str],
) -> None:
    parms = get_attrs(
        values,
        {
            "contour_num": f"{base}(3006,0048)",
            "attached_contours": f"{base}(3006,0049)",
            "geometric_type": f"{base}(3006,0042)",
            "slab_thickness": f"{base}(3006,0044)",
            "offset_vector": f"{base}(3006,0045)",
            "number_points": f"{base}(3006,0046)",
        },
        {
            "attached_contours": "MultiText",
            "offset_vector": "MultiText",
        },
        errors,
    )
    # Contour data itself is deliberately not stored; the Perl has the
    # column and the read commented out.
    roi_contour_id = db.insert_returning(
        "insert into roi_contour"
        " (roi_id, contour_num, geometric_type, slab_thickness,"
        "  offset_vector, number_of_points, roi_contour_attachment)"
        " values (%s, %s, %s, %s, %s, %s, %s)",
        [
            roi_id,
            parms.get("contour_num"),
            parms.get("geometric_type"),
            parms.get("slab_thickness"),
            parms.get("offset_vector"),
            parms.get("number_points"),
            parms.get("attached_contours"),
        ],
        "roi_contour_id",
    )

    for (image_item,) in values.substitutions(f"{base}(3006,0016)[<0>]"):
        image = f"{base}(3006,0016)[{image_item}]"
        parms = get_attrs(
            values,
            {
                "sop_class": f"{image}(0008,1150)",
                "sop_inst": f"{image}(0008,1155)",
                "frame": f"{image}(0008,1160)",
            },
            {"frame": "MultiText"},
            errors,
        )
        if not parms.get("sop_inst"):
            errors.append(f"Undefined sop_inst in {image}")
            continue
        if not parms.get("sop_class"):
            errors.append(f"Undefined sop_class in {image}")
            continue
        db.execute(
            "insert into contour_image"
            " (roi_contour_id, sop_class, sop_instance, frame_number)"
            " values (%s, %s, %s, %s)",
            [
                roi_contour_id,
                parms.get("sop_class"),
                parms.get("sop_inst"),
                parms.get("frame"),
            ],
        )


def rt_roi_observations(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RtRoiObservations``."""
    rois = hist.get("roi", {})
    for (obs_item,) in values.substitutions("(3006,0080)[<0>](3006,0082)"):
        base = f"(3006,0080)[{obs_item}]"
        parms = get_attrs(
            values,
            {
                "ob_num": f"{base}(3006,0082)",
                "ref_roi_num": f"{base}(3006,0084)",
                "obs_label": f"{base}(3006,0085)",
                "obs_desc": f"{base}(3006,0088)",
                "int_type": f"{base}(3006,00a4)",
                "interpreter": f"{base}(3006,00a6)",
                "material_id": f"{base}(3006,00e1)",
            },
            {},
            errors,
        )
        if _key(parms.get("ref_roi_num")) not in rois:
            errors.append(
                f"ROI observation item {obs_item} references non-existent "
                f"ROI {_render(parms.get('ref_roi_num'))}"
            )
            continue
        roi_id = rois[_key(parms.get("ref_roi_num"))]["roi_id"]

        observation_id = db.insert_returning(
            "insert into roi_observation"
            " (roi_id, roi_obs_num, observation_label,"
            "  observation_description, interpreted_type, interpreter,"
            "  material_id) values (%s, %s, %s, %s, %s, %s, %s)",
            [
                roi_id,
                parms.get("ob_num"),
                parms.get("obs_label"),
                parms.get("obs_desc"),
                parms.get("int_type"),
                parms.get("interpreter"),
                parms.get("material_id"),
            ],
            "roi_observation_id",
        )

        _related_rois(db, values, base, roi_id, rois, errors)
        _related_observations(db, values, base, observation_id)
        _physical_properties(db, values, base, observation_id)


def _related_rois(
    db: "Database",
    values: ParsedValues,
    base: str,
    roi_id: object,
    rois: dict,
    errors: list[str],
) -> None:
    for (item,) in values.substitutions(f"{base}(3006,0030)[<0>]"):
        related = f"{base}(3006,0030)[{item}]"
        rel_roi_num = values.get(f"{related}(3006,0084)")
        relationship = values.get(f"{related}(3006,0033)")
        if _key(rel_roi_num) not in rois:
            errors.append(
                f"ROI {roi_id} is related to undefined ROI number "
                f"{_render(rel_roi_num)}"
            )
            continue
        db.execute(
            "insert into roi_related_roi"
            " (roi_id, related_roi_id, relationship) values (%s, %s, %s)",
            [roi_id, rois[_key(rel_roi_num)]["roi_id"], relationship],
        )


def _related_observations(
    db: "Database", values: ParsedValues, base: str, observation_id: object
) -> None:
    for (item,) in values.substitutions(f"{base}(3006,00a0)[<0>](3006,0082)"):
        rel_obs_num = values.get(f"{base}(3006,00a0)[{item}](3006,0082)")
        db.execute(
            "insert into related_roi_observations"
            " (roi_observation_id, related_roi_observation_num)"
            " values (%s, %s)",
            [observation_id, rel_obs_num],
        )


def _physical_properties(
    db: "Database", values: ParsedValues, base: str, observation_id: object
) -> None:
    for (item,) in values.substitutions(f"{base}(3006,00b0)[<0>]"):
        prop = f"{base}(3006,00b0)[{item}]"
        # Note the column name: the schema spells it "phyical".
        properties_id = db.insert_returning(
            "insert into roi_physical_properties"
            " (roi_observation_id, property, property_value)"
            " values (%s, %s, %s)",
            [
                observation_id,
                values.get(f"{prop}(3006,00b2)"),
                values.get(f"{prop}(3006,00b4)"),
            ],
            "roi_phyical_properties_id",
        )

        if not fixes.ACTIVE.elemental_composition:
            # roi_elemental_composition is unreachable in the Perl, for two
            # independent reasons, so the faithful behaviour is to write
            # nothing at all:
            #
            #  1. It walks (3006,00a0) -- the related-observations sequence
            #     -- with the index from this physical-properties loop,
            #     instead of (3006,00b0) where the composition actually
            #     lives.
            #  2. Its insert calls currval on
            #     'roi_physical_properties_roi_physical_properties_id_seq',
            #     which does not exist: the real sequence carries the
            #     schema's "phyical" typo. Under DBI's default RaiseError=0
            #     that prints an error and inserts nothing.
            #
            # See posda.ingest.fixes to write these rows properly.
            continue

        for (element_item,) in values.substitutions(f"{prop}(3006,00b6)[<0>]"):
            element = f"{prop}(3006,00b6)[{element_item}]"
            db.execute(
                "insert into roi_elemental_composition"
                " (roi_phyical_properties_id,"
                "  roi_elemental_composition_atomic_number,"
                "  roi_elemental_composition_atomic_mass_fraction)"
                " values (%s, %s, %s)",
                [
                    properties_id,
                    values.get(f"{element}(3006,00b7)"),
                    values.get(f"{element}(3006,00b8)"),
                ],
            )


def _render(value: object) -> str:
    return "" if value is None else str(value)
