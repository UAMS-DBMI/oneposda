"""Handlers ported from ``Posda::DB::Modules``.

Each handler has the same contract as the Perl: it is called with the
database, the parsed dataset, the file id, a ``hist`` dict threaded between
handlers within one file, and an ``errors`` list whose contents become
``dicom_process_errors`` rows.

``hist`` matters for ordering. ``ImagePixel`` publishes ``image_id``, and
``ImagePlane``, ``SlopeIntercept`` and ``WindowLevel`` all abort without it,
so the handler lists in ``iod.py`` must keep ImagePixel first -- the Perl
relies on the same ordering.

Roughly twenty of the Perl's handlers are ``print "... not yet implemented"``
stubs; they are listed in ``STUBS`` and registered as no-ops.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from posda.ingest import fixes, rt_dose, rt_plan, rt_structure, specs
from posda.ingest.coercions import get_attrs
from posda.ingest.specs import AttrSpec
from posda.ingest.values import ParsedValues

if TYPE_CHECKING:  # avoids a psycopg2 import for callers that only parse
    from posda.ingest.db import Database

log = logging.getLogger(__name__)

PIXEL_DATA_TAG = 0x7FE00010


@dataclass(frozen=True)
class SimpleInsert:
    """A handler that is one attribute read followed by one INSERT.

    ``columns`` is ordered ``(column_name, parameter_name)``; the two differ
    in a few places (``file_patient.time_ob`` comes from ``tob``).
    """

    spec: AttrSpec
    table: str
    columns: tuple[tuple[str, str], ...]

    def __call__(
        self,
        db: Database,
        values: ParsedValues,
        file_id: int,
        hist: dict,
        errors: list[str],
    ) -> None:
        parms = get_attrs(values, self.spec.params, self.spec.coercions, errors)
        insert(db, self.table, file_id, parms, self.columns)


def insert(
    db: "Database",
    table: str,
    file_id: int,
    parms: dict,
    columns: tuple[tuple[str, str], ...],
) -> None:
    names = ["file_id"] + [column for column, _ in columns]
    placeholders = ", ".join(["%s"] * len(names))
    params = [file_id] + [parms.get(key) for _, key in columns]
    db.execute(
        f"insert into {table} ({', '.join(names)}) values ({placeholders})",
        params,
    )


patient = SimpleInsert(
    spec=specs.PATIENT,
    table="file_patient",
    columns=(
        ("patient_name", "patient_name"),
        ("patient_id", "patient_id"),
        ("id_issuer", "id_issuer"),
        ("dob", "dob"),
        ("sex", "sex"),
        ("time_ob", "tob"),
        ("other_ids", "other_ids"),
        ("other_names", "other_names"),
        ("ethnic_group", "ethnic_group"),
        ("comments", "comments"),
        ("patient_age", "patient_age"),
    ),
)

study = SimpleInsert(
    spec=specs.STUDY,
    table="file_study",
    columns=(
        ("study_instance_uid", "study_instance_uid"),
        ("study_date", "study_date"),
        ("study_time", "study_time"),
        ("referring_phy_name", "referring_phy_name"),
        ("study_id", "study_id"),
        ("accession_number", "accession_number"),
        ("study_description", "study_description"),
        ("phys_of_record", "phys_of_record"),
        ("phys_reading", "phys_reading"),
        ("admitting_diag", "admitting_diag"),
    ),
)

equipment = SimpleInsert(
    spec=specs.EQUIPMENT,
    table="file_equipment",
    columns=(
        ("manufacturer", "manufacturer"),
        ("institution_name", "institution_name"),
        ("institution_addr", "institution_addr"),
        ("station_name", "station_name"),
        ("inst_dept_name", "inst_dept_name"),
        ("manuf_model_name", "manuf_model_name"),
        ("dev_serial_num", "dev_serial_num"),
        ("software_versions", "software_versions"),
        ("spatial_resolution", "spatial_resolution"),
        ("last_calib_date", "last_calib_date"),
        ("last_calib_time", "last_calib_time"),
        ("pixel_pad", "pixel_pad"),
    ),
)

ct_image = SimpleInsert(
    spec=specs.CT_IMAGE,
    table="file_ct_image",
    columns=(
        ("kvp", "kvp"),
        ("instance_number", "instance_number"),
        ("scan_options", "scan_options"),
        ("data_collection_diameter", "data_collection_diameter"),
        ("reconstruction_diameter", "reconstruction_diameter"),
        ("dist_source_to_pat", "dist_source_to_pat"),
        ("dist_source_to_detect", "dist_source_to_detect"),
        ("gantry_tilt", "gantry_tilt"),
        ("rotation_dir", "rotation_dir"),
        ("exposure_time", "exposure_time"),
        ("exposure", "exposure"),
        ("xray_tube_current", "xray_tube_current"),
        ("filter_type", "filter_type"),
        ("generator_power", "generator_power"),
        ("convolution_kernal", "convolution_kernal"),
        ("table_feed_per_rot", "table_feed_per_rot"),
    ),
)

_SERIES_COLUMNS = (
    ("modality", "modality"),
    ("series_instance_uid", "series_instance_uid"),
    ("series_number", "series_number"),
    ("laterality", "laterality"),
    ("series_date", "series_date"),
    ("series_time", "series_time"),
    ("performing_phys", "performing_phys"),
    ("protocol_name", "protocol_name"),
    ("series_description", "series_description"),
    ("operators_name", "operators_name"),
    ("body_part_examined", "body_part_examined"),
    ("patient_position", "patient_position"),
    ("smallest_pixel_value", "smallest_pixel_value"),
    ("largest_pixel_value", "largest_pixel_value"),
    ("performed_procedure_step_id", "performed_procedure_step_id"),
    ("performed_procedure_step_start_date", "performed_procedure_start_date"),
    ("performed_procedure_step_start_time", "performed_procedure_start_time"),
    ("performed_procedure_step_desc", "performed_procedure_desc"),
    ("performed_procedure_step_comments", "performed_procedure_comments"),
)


def series(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    parms = get_attrs(values, specs.SERIES.params, specs.SERIES.coercions, errors)
    if parms.get("series_instance_uid") is None:
        errors.append("Series instance UID undefined")
        return
    insert(db, "file_series", file_id, parms, _SERIES_COLUMNS)


def frame_of_reference(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    parms = get_attrs(
        values,
        specs.FRAME_OF_REFERENCE.params,
        specs.FRAME_OF_REFERENCE.coercions,
        errors,
    )
    db.execute(
        "insert into file_for (file_id, for_uid, position_ref_indicator)"
        " values (%s, %s, %s)",
        [file_id, parms.get("for_uid"), parms.get("position_ref_indicator")],
    )
    hist["frame_of_reference"] = parms.get("for_uid")


def image_pixel(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``ImagePixel``.

    The pixel-dedup half of this handler is dead in the live configuration:
    ``Posda::NewTry`` parses with ``skip_large => 256``, so the pixel data
    element has no value, ``pixel_data`` stays undefined, and
    ``unique_pixel_data``/``pixel_location`` are never written. The lookup
    that follows then runs ``where unique_pixel_data_id = NULL``, matches
    nothing, and a fresh ``image`` row is created for every file. Both tables
    are empty in the dev database and every ``image`` row has a NULL
    ``unique_pixel_data_id``, confirming this. It is reproduced rather than
    fixed so the port can be diff-verified; the fix is tracked separately.
    """
    raw = values.dataset.get_item(PIXEL_DATA_TAG)
    if raw is None:
        errors.append("No pixel data in ImagePixel")
        return

    unique_pixel_data_id = None
    pixel_data = _pixel_value(values, raw)
    if pixel_data is not None:
        pixel_digest = hashlib.md5(pixel_data).hexdigest()
        pixel_size = len(pixel_data)
        existing = db.fetchone(
            "select * from unique_pixel_data where digest = %s and size = %s",
            [pixel_digest, pixel_size],
        )
        if existing is not None:
            unique_pixel_data_id = existing["unique_pixel_data_id"]
            hist["already_existing_pixel_data"] = 1
        else:
            unique_pixel_data_id = db.insert_returning(
                "insert into unique_pixel_data (digest, size) values (%s, %s)",
                [pixel_digest, pixel_size],
                "unique_pixel_data_id",
            )
        if unique_pixel_data_id is not None:
            db.execute(
                "insert into pixel_location"
                " (unique_pixel_data_id, file_id, file_offset)"
                " values (%s, %s, %s)",
                [unique_pixel_data_id, file_id, getattr(raw, "value_tell", None)],
            )
    hist["unique_pixel_data_id"] = unique_pixel_data_id

    parms = get_attrs(
        values, specs.IMAGE_PIXEL.params, specs.IMAGE_PIXEL.coercions, errors
    )
    image_id = _matching_image(db, parms, unique_pixel_data_id, file_id, hist, errors)
    if image_id is None:
        image_id = db.insert_returning(
            "insert into image"
            " (image_type, samples_per_pixel, photometric_interpretation,"
            "  pixel_rows, pixel_columns, bits_allocated, bits_stored,"
            "  high_bit, pixel_representation, planar_configuration,"
            "  number_of_frames, unique_pixel_data_id, pixel_spacing)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                parms.get("image_type"),
                parms.get("samples_per_pixel"),
                parms.get("photometric_interpretation"),
                parms.get("pixel_rows"),
                parms.get("pixel_columns"),
                parms.get("bits_allocated"),
                parms.get("bits_stored"),
                parms.get("high_bit"),
                parms.get("pixel_representation"),
                parms.get("planar_configuration"),
                parms.get("number_of_frames"),
                unique_pixel_data_id,
                parms.get("pixel_spacing"),
            ],
            "image_id",
        )

    db.execute(
        "insert into file_image (file_id, image_id, content_date, content_time)"
        " values (%s, %s, %s, %s)",
        [file_id, image_id, parms.get("content_date"), parms.get("content_time")],
    )
    hist["image_id"] = image_id


def _pixel_value(values: ParsedValues, raw: object) -> bytes | None:
    """The pixel bytes, or None when Posda would not have loaded them."""
    value = getattr(raw, "value", None)
    if not isinstance(value, bytes):
        return None
    if values.skip_large and len(value) > values.skip_large:
        return None
    return value


def _matching_image(
    db: "Database",
    parms: dict,
    unique_pixel_data_id: object,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> object:
    """Find an existing image row sharing this pixel data.

    Compares every attribute except content date/time, recording a complaint
    for each field that differs, exactly as the Perl does.
    """
    compared = [key for key in parms if key not in ("content_date", "content_time")]
    for row in db.fetchall(
        "select * from image where unique_pixel_data_id = %s",
        [unique_pixel_data_id],
    ):
        same = True
        for key in compared:
            new, old = parms.get(key), row.get(key)
            if _differs(new, old):
                errors.append(
                    f"Same pixel data with different {key}: "
                    f'"{_render(old)}" vs "{_render(new)}"\n'
                    f"old_image_id: {row.get('image_id')}\n"
                    f"file_id: {file_id}"
                )
                same = False
        if same:
            hist["already_existing_image"] = 1
            return row.get("image_id")
    return None


def _differs(new: object, old: object) -> bool:
    if (new is None) != (old is None):
        return True
    if new is None:
        return False
    return str(new) != str(old)


def _render(value: object) -> str:
    return "<undef>" if value is None else str(value)


def image_plane(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    if hist.get("image_id") is None:
        errors.append("no image_id in ImagePlane")
        return
    parms = get_attrs(
        values, specs.IMAGE_PLANE.params, specs.IMAGE_PLANE.coercions, errors
    )
    row = db.fetchone(
        "select * from image_geometry where image_id = %s and ipp = %s"
        " and iop = %s and for_uid = %s",
        [hist["image_id"], parms.get("ipp"), parms.get("iop"), parms.get("for_uid")],
    )
    if row is not None and row.get("image_geometry_id") is not None:
        image_geometry_id = row["image_geometry_id"]
    else:
        image_geometry_id = db.insert_returning(
            "insert into image_geometry (image_id, iop, ipp, for_uid)"
            " values (%s, %s, %s, %s)",
            [
                hist["image_id"],
                parms.get("iop"),
                parms.get("ipp"),
                parms.get("for_uid"),
            ],
            "image_geometry_id",
        )
    if image_geometry_id is None:
        raise RuntimeError("couldn't define an image geometry")
    db.execute(
        "insert into file_image_geometry (file_id, image_geometry_id)"
        " values (%s, %s)",
        [file_id, image_geometry_id],
    )


def slope_intercept(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    if hist.get("image_id") is None:
        errors.append("No image_id in SlopeIntercept")
        return
    slope = values.get("(0028,1053)")
    intercept = values.get("(0028,1052)")
    units = values.get("(0054,1001)")
    if slope is None or intercept is None:
        errors.append(f"no slope intercept for file {file_id}")
        return

    if fixes.ACTIVE.lookup_upsert:
        si_id = db.fetchone(
            "insert into slope_intercept (slope, intercept, si_units)"
            " values (%s, %s, %s)"
            " on conflict (slope, intercept, si_units)"
            " do update set slope = excluded.slope"
            " returning slope_intercept_id",
            [slope, intercept, units],
        )["slope_intercept_id"]
        _link_slope_intercept(db, si_id, hist["image_id"], file_id)
        return

    if units is not None:
        row = db.fetchone(
            "select * from slope_intercept"
            " where slope = %s and intercept = %s and si_units = %s",
            [slope, intercept, units],
        )
    else:
        row = db.fetchone(
            "select * from slope_intercept"
            " where slope = %s and intercept = %s and si_units is null",
            [slope, intercept],
        )

    if row is not None:
        si_id = row["slope_intercept_id"]
    else:
        si_id = db.insert_returning(
            "insert into slope_intercept (slope, intercept, si_units)"
            " values (%s, %s, %s)",
            [slope, intercept, units],
            "slope_intercept_id",
        )

    _link_slope_intercept(db, si_id, hist["image_id"], file_id)


def _link_slope_intercept(
    db: "Database", si_id: object, image_id: object, file_id: int
) -> None:
    existing = db.fetchone(
        "select * from image_slope_intercept"
        " where image_id = %s and slope_intercept_id = %s",
        [image_id, si_id],
    )
    if existing is None:
        db.execute(
            "insert into image_slope_intercept (slope_intercept_id, image_id)"
            " values (%s, %s)",
            [si_id, image_id],
        )
    db.execute(
        "insert into file_slope_intercept (slope_intercept_id, file_id)"
        " values (%s, %s)",
        [si_id, file_id],
    )


def window_level(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``WindowLevel``, including two defects worth knowing about.

    First, the handler requires window centre and width to arrive as lists.
    They do -- but only because (0028,1050)/(0028,1051) carry dictionary VM
    ``1-n``, so Posda's parser boxes even a single value. This is the
    handler that makes the dictionary-VM behaviour load-bearing.

    Second, when a window explanation is present the Perl nests two loops
    that both use ``$i``; the inner shadows the outer, so the complete inner
    loop runs once per explanation and ``file_win_lev`` receives N^2 rows
    instead of N. Files without an explanation take the else branch and are
    unaffected, which is why the dev database shows no duplication.
    """
    if hist.get("image_id") is None:
        errors.append("No image_id in WindowLevel")
        return
    centre = values.get("(0028,1050)")
    width = values.get("(0028,1051)")
    explanation = values.get("(0028,1055)")

    if centre is None or width is None:
        return
    if not isinstance(centre, list) or not isinstance(width, list):
        return
    if len(centre) != len(width):
        return

    if explanation is not None:
        if not isinstance(explanation, list) or len(explanation) != len(width):
            return
        # The Perl runs the inner loop once per explanation because both
        # loops use $i and the inner shadows the outer. Reproduced by
        # default; see posda.ingest.fixes.
        repeats = 1 if fixes.ACTIVE.window_level_duplication else len(explanation)
        for _ in range(repeats):
            for index in range(len(centre)):
                win_lev_id = _window_level_id(
                    db, width[index], centre[index], explanation[index]
                )
                _link_window_level(db, win_lev_id, hist["image_id"], file_id, index)
    else:
        for index in range(len(centre)):
            win_lev_id = _window_level_id(db, width[index], centre[index], None)
            _link_window_level(db, win_lev_id, hist["image_id"], file_id, index)


def _window_level_id(
    db: "Database", width: object, centre: object, explanation: object
) -> object:
    if fixes.ACTIVE.lookup_upsert:
        return _upsert_window_level(db, width, centre, explanation)

    if explanation is not None:
        row = db.fetchone(
            "select * from window_level"
            " where window_width = %s and window_center = %s"
            " and win_lev_desc = %s",
            [width, centre, explanation],
        )
        if row is not None:
            return row["window_level_id"]
        return db.insert_returning(
            "insert into window_level (window_width, window_center, win_lev_desc)"
            " values (%s, %s, %s)",
            [width, centre, explanation],
            "window_level_id",
        )
    row = db.fetchone(
        "select * from window_level"
        " where window_width = %s and window_center = %s and win_lev_desc is null",
        [width, centre],
    )
    if row is not None:
        return row["window_level_id"]
    return db.insert_returning(
        "insert into window_level (window_width, window_center) values (%s, %s)",
        [width, centre],
        "window_level_id",
    )


def _upsert_window_level(
    db: "Database", width: object, centre: object, explanation: object
) -> object:
    """Race-free lookup, requiring window_level_natural_key.

    The check-then-insert above lets two concurrent workers both miss and
    both insert. ON CONFLICT collapses that into one row; DO UPDATE rather
    than DO NOTHING so the id comes back on the conflicting path too.
    """
    row = db.fetchone(
        "insert into window_level (window_width, window_center, win_lev_desc)"
        " values (%s, %s, %s)"
        " on conflict (window_width, window_center, win_lev_desc)"
        " do update set window_width = excluded.window_width"
        " returning window_level_id",
        [width, centre, explanation],
    )
    return row["window_level_id"]


def _link_window_level(
    db: "Database", win_lev_id: object, image_id: object, file_id: int, index: int
) -> None:
    existing = db.fetchone(
        "select * from image_window_level"
        " where window_level_id = %s and image_id = %s",
        [win_lev_id, image_id],
    )
    if existing is None:
        db.execute(
            "insert into image_window_level (window_level_id, image_id)"
            " values (%s, %s)",
            [win_lev_id, image_id],
        )
    db.execute(
        "insert into file_win_lev (window_level_id, file_id, wl_index)"
        " values (%s, %s, %s)",
        [win_lev_id, file_id, index],
    )


# Handlers that are print-only stubs in Modules.pm. Kept as named no-ops so
# the SOP-class handler lists in iod.py can stay a line-for-line transcription
# of the Perl's.
STUBS = (
    "AcquisitionContext",
    "ContrastBolus",
    "CRImage",
    "DeformableSpatialRegistration",
    "Document",
    "DXImage",
    "KeyObjectDocument",
    "KeySeries",
    "MRImage",
    "PetImage",
    "PresentationState",
    "RealWorldMapping",
    "Retired",
    "RtBrachy",
    "Segmentation",
    "SpatialFiducials",
    "SpatialRegistration",
    "SRSeries",
    "SurfaceSegmentation",
    "Synchronization",
    "UnImplemented",
    "USImage",
    "Waveform",
    "WaveformIdentification",
)


def _make_stub(name: str):
    def stub(
        db: Database,
        values: ParsedValues,
        file_id: int,
        hist: dict,
        errors: list[str],
    ) -> None:
        log.debug("%s Module not yet implemented", name)

    stub.__name__ = f"stub_{name}"
    return stub


HANDLERS: dict[str, object] = {
    "Patient": patient,
    "Study": study,
    "Series": series,
    "Equipment": equipment,
    "ImagePixel": image_pixel,
    "ImagePlane": image_plane,
    "FrameOfReference": frame_of_reference,
    "SlopeIntercept": slope_intercept,
    "WindowLevel": window_level,
    "CTImage": ct_image,
    "StructureSet": rt_structure.structure_set,
    "RoiContour": rt_structure.roi_contour,
    "RtRoiObservations": rt_structure.rt_roi_observations,
    "RTDose": rt_dose.rt_dose,
    "RTDvh": rt_dose.rt_dvh,
    "RtPlan": rt_plan.rt_plan,
    "RtPrescription": rt_plan.rt_prescription,
    "RtToleranceTables": rt_plan.rt_tolerance_tables,
    "RtPatientSetup": rt_plan.rt_patient_setup,
    "RtFractionScheme": rt_plan.rt_fraction_scheme,
}
HANDLERS.update({name: _make_stub(name) for name in STUBS})
