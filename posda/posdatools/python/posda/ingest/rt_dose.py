"""RT Dose handlers, ported from ``Posda::DB::Modules``.

``RTDose`` runs after ``ImagePixel`` and consumes the ``image_id`` it
publishes; it then publishes ``rt_dose_id`` for ``RTDvh``. Both run only for
the RT Dose SOP class.

``RTDvh`` is the one handler that reads private elements from inside
sequence items -- the ITC_DVH_Computation and ITC_for_RTOG_Conversion
blocks -- which is why signature parsing has to resolve private creators at
any depth rather than only at the root.
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

PIXEL_DATA_SIG = "(7fe0,0010)"


def rt_dose(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RTDose``."""
    parms = get_attrs(
        values,
        {
            "dose_units": "(3004,0002)",
            "dose_type": "(3004,0004)",
            "dose_instance_number": "(0020,0013)",
            "dose_comment": "(3004,0006)",
            "normalization_point": "(3004,0008)",
            "dose_summation_type": "(3004,000a)",
            "referenced_plan_class": "(300c,0002)[0](0008,1150)",
            "referenced_plan_uid": "(300c,0002)[0](0008,1155)",
            "tissue_heterogeneity": "(3004,0014)",
        },
        {
            "tissue_heterogeneity": "MultiText",
            "normalization_point": "MultiText",
        },
        errors,
    )

    dose_id = db.insert_returning(
        "insert into rt_dose"
        " (rt_dose_units, rt_dose_type, rt_dose_instance_number,"
        "  rt_dose_comment, rt_dose_normalization_point,"
        "  rt_dose_summation_type, rt_dose_referenced_plan_class,"
        "  rt_dose_referenced_plan_uid, rt_dose_tissue_heterogeneity)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            parms.get("dose_units"),
            parms.get("dose_type"),
            parms.get("dose_instance_number"),
            parms.get("dose_comment"),
            # The Perl passes $parms{normalizaton_point} -- missing an "i" --
            # so this column is unconditionally NULL. Reproduced by default;
            # see posda.ingest.fixes.
            (
                parms.get("normalization_point")
                if fixes.ACTIVE.dose_normalization_point
                else None
            ),
            parms.get("dose_summation_type"),
            parms.get("referenced_plan_class"),
            parms.get("referenced_plan_uid"),
            parms.get("tissue_heterogeneity"),
        ],
        "rt_dose_id",
    )
    hist["rt_dose_id"] = dose_id
    db.execute(
        "insert into file_dose (rt_dose_id, file_id) values (%s, %s)",
        [dose_id, file_id],
    )

    # rt_dose_image is written only when the pixel data has a value, which
    # under skip_large=256 means only for grids of 256 bytes or less. Real
    # dose grids are far larger, so in production this row is never created.
    if values.get(PIXEL_DATA_SIG) is None:
        return
    image_parms = get_attrs(
        values,
        {"gfov": "(3004,000c)", "scaling": "(3004,000e)"},
        {"gfov": "MultiText"},
        errors,
    )
    db.execute(
        "insert into rt_dose_image"
        " (rt_dose_id, image_id, rt_dose_grid_frame_offset_vector,"
        "  rt_dose_grid_scaling) values (%s, %s, %s, %s)",
        [
            dose_id,
            hist.get("image_id"),
            image_parms.get("gfov"),
            image_parms.get("scaling"),
        ],
    )


def rt_dvh(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RTDvh``."""
    dvh_items = values.search("(3004,0050)[<0>](3004,0002)")
    if not dvh_items:
        return

    parms = get_attrs(
        values,
        {
            "dvh_normalization_point": "(3004,0040)",
            "dvh_normalization_value": "(3004,0042)",
            "referenced_struct_class": "(300c,0060)[0](0008,1150)",
            "referenced_struct_uid": "(300c,0060)[0](0008,1155)",
        },
        {"dvh_normalization_point": "MultiText"},
        errors,
    )

    # Source falls back to the series description, then to "Unknown".
    source = values.get('(3005,"ITC_DVH_Computation",50)')
    if source is None:
        source = values.get("(0008,103e)")
    if source is None:
        source = "Unknown"

    rt_dvh_id = db.insert_returning(
        "insert into rt_dvh"
        " (rt_dvh_referenced_ss_class, rt_dvh_source,"
        "  rt_dvh_referenced_ss_uid, rt_dvh_normalization_point,"
        "  rt_dvh_normalization_value) values (%s, %s, %s, %s, %s)",
        [
            parms.get("referenced_struct_class"),
            source,
            parms.get("referenced_struct_uid"),
            parms.get("dvh_normalization_point"),
            parms.get("dvh_normalization_value"),
        ],
        "rt_dvh_id",
    )
    db.execute(
        "insert into rt_dvh_rt_dose (rt_dose_id, rt_dvh_id) values (%s, %s)",
        [hist.get("rt_dose_id"), rt_dvh_id],
    )

    for (dvh_item,) in dvh_items:
        _dvh(db, values, dvh_item, rt_dvh_id, errors)


def _dvh(
    db: "Database",
    values: ParsedValues,
    dvh_item: int,
    rt_dvh_id: object,
    errors: list[str],
) -> None:
    base = f"(3004,0050)[{dvh_item}]"
    parms = get_attrs(
        values,
        {
            "dvh_type": f"{base}(3004,0001)",
            "dose_units": f"{base}(3004,0002)",
            "dose_type": f"{base}(3004,0004)",
            "dose_scaling": f"{base}(3004,0052)",
            "dose_volume_units": f"{base}(3004,0054)",
            "number_of_bins": f"{base}(3004,0056)",
            "dvh_data": f"{base}(3004,0058)",
            "minimum_dose": f"{base}(3004,0070)",
            "maximum_dose": f"{base}(3004,0072)",
            "mean_dose": f"{base}(3004,0074)",
        },
        {"dvh_data": "MultiText"},
        errors,
    )

    rtog = f'{base}(3005,"ITC_for_RTOG_Conversion",'
    itc = f'{base}(3005,"ITC_DVH_Computation",'
    simple_name = values.get(f"{rtog}26)")
    match_name = values.get(f"{rtog}28)")
    plan_name = values.get(f"{rtog}2a)")
    plan_desc = values.get(f"{rtog}2c)")
    arm = values.get(f"{rtog}2e)")
    prescription = values.get(f"{rtog}30)")
    heterogeneity = values.get(f"{itc}01)")
    summation_id = values.get(f"{itc}02)")
    manufacturer = values.get(f"{itc}03)")
    model_name = values.get(f"{itc}04)")
    grid_class = values.get(f"{itc}05)[0](0008,1150)")
    grid_uid = values.get(f"{itc}05)[0](0008,1155)")

    arm = _as_integer(arm)

    rt_dvh_dvh_id = db.insert_returning(
        "insert into rt_dvh_dvh"
        " (rt_dvh_id, rt_dvh_dvh_type, rt_dvh_dvh_dose_units,"
        "  rt_dvh_dvh_dose_type, rt_dvh_dvh_roi_alt_name,"
        "  rt_dvh_dvh_roi_alt_desc, rt_dvh_dvh_plan_id,"
        "  rt_dvh_dvh_plan_desc, rt_dvh_dvh_arm, rt_dvh_dvh_prescription,"
        "  rt_dvh_dvh_dose_scaling, rt_dvh_dvh_dose_volume_units,"
        "  rt_dvh_dvh_dose_number_of_bins, rt_dvh_dvh_minimum_dose,"
        "  rt_dvh_dvh_maximum_dose, rt_dvh_dvh_mean_dose,"
        "  rt_dvh_dvh_text_data, rt_dvh_dvh_specified_heterogeneity,"
        "  rt_dvh_dvh_dose_summation_id, rt_dvh_dvh_dose_manufacturer,"
        "  rt_dvh_dvh_dose_model_name,"
        "  rt_dvh_dvh_referenced_dose_grid_class,"
        "  rt_dvh_dvh_referenced_dose_grid_uid)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
        "         %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            rt_dvh_id,
            parms.get("dvh_type"),
            parms.get("dose_units"),
            parms.get("dose_type"),
            simple_name,
            match_name,
            plan_name,
            plan_desc,
            arm,
            prescription,
            parms.get("dose_scaling"),
            parms.get("dose_volume_units"),
            parms.get("number_of_bins"),
            parms.get("minimum_dose"),
            parms.get("maximum_dose"),
            parms.get("mean_dose"),
            parms.get("dvh_data"),
            heterogeneity,
            summation_id,
            manufacturer,
            model_name,
            grid_class,
            grid_uid,
        ],
        "rt_dvh_dvh_id",
    )

    for (roi_item,) in values.search(f"{base}(3004,0060)[<0>](3006,0084)"):
        roi = f"{base}(3004,0060)[{roi_item}]"
        roi_parms = get_attrs(
            values,
            {
                "referenced_roi": f"{roi}(3006,0084)",
                "roi_contribution_type": f"{roi}(3004,0062)",
            },
            {},
            errors,
        )
        db.execute(
            "insert into rt_dvh_dvh_roi"
            " (rt_dvh_dvh_id, rt_dvh_dvh_ref_roi_number,"
            "  rt_dvh_dvh_roi_cont_type) values (%s, %s, %s)",
            [
                rt_dvh_dvh_id,
                roi_parms.get("referenced_roi"),
                roi_parms.get("roi_contribution_type"),
            ],
        )


def _as_integer(arm: object) -> object:
    """Truncate the study arm, complaining as the Perl does.

    The Perl compares ``$arm == int $arm`` and prints to stderr on a
    mismatch; the stored value is the truncated one either way.
    """
    if arm is None:
        return None
    try:
        number = float(str(arm))
    except ValueError:
        return arm
    truncated = int(number)
    if truncated != number:
        log.warning("arm (%s) isn't int", arm)
    return truncated
