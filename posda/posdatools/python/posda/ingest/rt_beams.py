"""``RtBeams``, ported from ``Posda::DB::Modules``.

The largest handler in the module: one loop over the beam sequence, ten
sub-loops for the things attached to a beam, and a control-point loop with
four sub-loops of its own. Every row is keyed by (plan_id, beam_number) --
and control point rows additionally by control_point_index -- rather than by
a generated id, so nothing here needs RETURNING.

The parameter tables were extracted mechanically from the Perl rather than
retyped; between them they name a little over 130 elements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from posda.ingest import fixes
from posda.ingest.coercions import get_attrs
from posda.ingest.values import ParsedValues

if TYPE_CHECKING:
    from posda.ingest.db import Database

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubTable:
    """One of the sequences hanging off a beam.

    ``sequence`` is the tag of the sequence itself, ``key`` the element the
    Perl's Substitutions pattern terminates on, and ``params`` maps column
    name to the element signature within an item.
    """

    sequence: str
    key: str
    table: str
    params: dict[str, str]
    coercions: dict[str, str] = field(default_factory=dict)
    required: tuple[str, ...] = ()


BEAM_SEQUENCE = "(300a,00b0)"

_BEAM_PARAMS = {
    "beam_number": "(300a,00c0)",
    "beam_name": "(300a,00c2)",
    "beam_description": "(300a,00c3)",
    "beam_type": "(300a,00c4)",
    "radiation_type": "(300a,00c6)",
    "high_dose_technique": "(300a,00c7)",
    "treatement_machine_name": "(300a,00b2)",
    "manufacturer": "(0008,0070)",
    "institution_name": "(0008,0080)",
    "institution_address": "(0008,0081)",
    "institution_department_name": "(0008,1040)",
    "manufacturers_model_name": "(0008,1090)",
    "device_serial_number": "(0018,1000)",
    "primary_dosimeter_unit": "(300a,00b3)",
    "tolerance_table_number": "(300c,00a0)",
    "source_axis_distance": "(300a,00b4)",
    "patient_setup_number": "(300c,00ba)",
    "treatment_delivery_type": "(300a,00ce)",
    "number_of_wedges": "(300a,00d0)",
    "number_of_compensators": "(300a,00e0)",
    "total_compensator_tray_factor": "(300a,00e2)",
    "number_of_boli": "(300a,00ed)",
    "number_of_blocks": "(300a,00f0)",
    "total_block_tray_factor": "(300a,00f2)",
    "final_cumulative_meterset_weight": "(300a,010e)",
    "number_of_control_points": "(300a,0110)",
}

_SUB_TABLES = (
    SubTable(
        sequence="(300a,00b6)",
        key="(300a,00b8)",
        table="beam_limiting_device",
        params={
            "bld_type": "(300a,00b8)",
            "source_to_bld_distance": "(300a,00ba)",
            "number_of_leaf_jaw_pairs": "(300a,00bc)",
            "leaf_position_boundries": "(300a,00be)",
        },
        coercions={"leaf_position_boundries": "MultiText"},
        required=("bld_type",),
    ),
    SubTable(
        sequence="(300c,0042)",
        key="(0008,1155)",
        table="image_referenced_from_beam",
        params={
            "sop_class_uid": "(0008,1150)",
            "sop_instance_uid": "(0008,1155)",
            "reference_image_number": "(300a,00c8)",
            "start_cum_meterset_weight": "(300c,0008)",
            "end_cum_meterset_weight": "(300c,0009)",
        },
        required=("sop_instance_uid", "sop_class_uid", "reference_image_number"),
    ),
    SubTable(
        sequence="(300a,00ca)",
        key="",  # the Perl's pattern terminates on the item itself
        table="planned_verification_images",
        params={
            "start_cum_meterset_weight": "(300c,0008)",
            "meterset_exposure": "(3002,0032)",
            "end_cum_meterset_weight": "(300c,0009)",
            "rt_image_plane": "(3002,000c)",
            "xray_image_receptor_angle": "(3002,000e)",
            "rt_image_orientation": "(3002,0010)",
            "rt_image_position": "(3002,0012)",
            "rt_image_sid": "(3002,0026)",
            "image_device_specific_acquisition_params": "(300a,00cc)",
            "referenced_reference_image_number": "(300c,0007)",
        },
        coercions={
            "rt_image_orientation": "MultiText",
            "rt_image_position": "MultiText",
        },
    ),
    SubTable(
        sequence="(300c,0080)",
        key="(0008,1155)",
        table="dose_referenced_from_beam",
        # Note the two are crossed in the Perl: sop_class_uid reads
        # (0008,1155) and sop_instance_uid reads (0008,1150).
        params={
            "sop_class_uid": "(0008,1155)",
            "sop_instance_uid": "(0008,1150)",
        },
    ),
    SubTable(
        sequence="(300a,00d1)",
        key="(300a,00d2)",
        table="beam_wedge",
        params={
            "wedge_number": "(300a,00d2)",
            "wedge_type": "(300a,00d3)",
            "wedge_id": "(300a,00d4)",
            "wedge_accessory_code": "(300a,00f9)",
            "wedge_angle": "(300a,00d5)",
            "wedge_factor": "(300a,00d6)",
            "wedge_orientation": "(300a,00d8)",
            "source_to_wedge_tray_distance": "(300a,00da)",
        },
    ),
    SubTable(
        sequence="(300a,00e3)",
        key="(300a,00e4)",
        table="beam_compensator",
        params={
            "compensator_number": "(300a,00e4)",
            "compensator_type": "(300a,00ee)",
            "compensator_description": "(300a,02eb)",
            "material_id": "(300a,00e1)",
            "compensator_id": "(300a,00e5)",
            "compensator_accessory_code": "(300a,00f9)",
            "source_to_compensator_tray_distance": "(300a,00e6)",
            "compensator_divergence": "(300a,02e0)",
            "compensator_mounting_position": "(300a,02e1)",
            "compensator_rows": "(300a,00e7)",
            "compensator_cols": "(300a,00e8)",
            "compensator_pixel_spacing": "(300a,00e9)",
            "compensator_position": "(300a,00ea)",
            "compensator_transmission_data": "(300a,00eb)",
            "compensator_thickness_data": "(300a,00ec)",
            "source_to_compensator_distance": "(300a,02e2)",
        },
        coercions={
            "compensator_pixel_spacing": "MultiText",
            "compensator_position": "MultiText",
            "compensator_transmission_data": "MultiText",
            "compensator_thickness_data": "MultiText",
            "source_to_compensator_distance": "MultiText",
        },
    ),
    SubTable(
        sequence="(300c,00b0)",
        key="(3006,0084)",
        table="beam_bolus",
        params={
            "referenced_roi_number": "(3006,0084)",
            "bolus_id": "(300a,00dc)",
            "bolus_accessory_code": "(300a,00f9)",
            "bolus_description": "(300a,00dd)",
        },
    ),
    SubTable(
        sequence="(300a,00f4)",
        key="(300a,00fc)",
        table="beam_block",
        params={
            "block_number": "(300a,00fc)",
            "block_tray_id": "(300a,00f5)",
            "block_accessory_code": "(300a,00f9)",
            "source_to_block_tray_distance": "(300a,00f6)",
            "block_type": "(300a,00f8)",
            "block_divergence": "(300a,00fa)",
            "block_mounting_position": "(300a,00fb)",
            "block_name": "(300a,00fe)",
            "material_id": "(300a,00e1)",
            "block_thickness": "(300a,0100)",
            "block_transmission": "(300a,0102)",
            "block_number_of_points": "(300a,0104)",
            "block_data": "(300a,0106)",
        },
        coercions={"block_data": "MultiText"},
    ),
    SubTable(
        sequence="(300a,0107)",
        key="(300a,0108)",
        table="beam_applicator",
        params={
            "applicator_id": "(300a,0108)",
            "applicator_accessory_code": "(300a,00f9)",
            "applicator_type": "(300a,0109)",
            "applicator_description": "(300a,010a)",
        },
    ),
)

_GENERAL_ACCESSORY = SubTable(
    sequence="(300a,0420)",
    key="(300a,0424)",
    table="beam_general_accessory",
    params={
        "general_accessory_number": "(300a,0424)",
        "general_accessory_id": "(300a,0421)",
        "general_accessory_description": "(300a,0422)",
        "general_accessory_type": "(300a,0423)",
        "general_accessory_code": "(300a,00f9)",
    },
    required=("general_accessory_code",),
)

_CONTROL_POINT_PARAMS = {
    "control_point_index": "(300a,0112)",
    "cumulative_meterset_weight": "(300a,0134)",
    "nominal_beam_energy": "(300a,0114)",
    "dose_rate_set": "(300a,0115)",
    "gantry_angle": "(300a,011e)",
    "gantry_rotation_direction": "(300a,011f)",
    "gantry_pitch_angle": "(300a,014a)",
    "gantry_pitch_rotation_direction": "(300a,014c)",
    "beam_limiting_device_angle": "(300a,0120)",
    "beam_limiting_device_rotation_direction": "(300a,0121)",
    "patient_support_angle": "(300a,0122)",
    "patient_support_rotation_direction": "(300a,0123)",
    "table_top_eccentric_axis_distance": "(300a,0124)",
    "table_top_eccentric_angle": "(300a,0125)",
    "table_top_eccentric_rotation_direction": "(300a,0126)",
    "table_top_pitch_angle": "(300a,0140)",
    "table_top_pitch_rotation_direction": "(300a,0142)",
    "table_top_roll_angle": "(300a,0144)",
    "table_top_roll_rotation_direction": "(300a,0146)",
    "table_top_vertical_position": "(300a,0128)",
    "table_top_longitudinal_position": "(300a,0129)",
    "table_top_lateral_position": "(300a,012a)",
    "isocenter_position": "(300a,012c)",
    "surface_entry_point": "(300a,012e)",
    "source_to_surface_distance": "(300a,0130)",
}

_CONTROL_POINT_SUB_TABLES = (
    SubTable(
        sequence="(300c,0050)",
        key="(300c,0051)",
        table="control_point_reference_dose",
        params={
            "referenced_dose_reference_number": "(300c,0051)",
            "cumulative_dose_ref_coefficent": "(300a,010c)",
        },
    ),
    SubTable(
        sequence="(300a,0080)",
        key="(0008,1150)",
        table="control_point_dose_reference",
        params={
            "sop_class_uid": "(0008,1150)",
            "sop_instance_uid": "(0008,1155)",
        },
    ),
    SubTable(
        sequence="(300a,0116)",
        key="(300c,00c0)",
        table="control_point_wedge_position",
        params={
            "wedge_number": "(300c,00c0)",
            "wedge_position": "(300a,0118)",
        },
    ),
    SubTable(
        sequence="(300a,011a)",
        key="(300a,00b8)",
        table="control_point_bld_position",
        params={
            "bld_type": "(300a,00b8)",
            "leaf_jaw_positions": "(300a,011c)",
        },
        coercions={"leaf_jaw_positions": "MultiText"},
    ),
)


def rt_beams(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RtBeams``."""
    plan_id = hist.get("plan_id")
    for (beam_item,) in values.substitutions(f"{BEAM_SEQUENCE}[<0>](300a,00c0)"):
        base = f"{BEAM_SEQUENCE}[{beam_item}]"
        parms = get_attrs(
            values,
            {name: f"{base}{sig}" for name, sig in _BEAM_PARAMS.items()},
            {},
            errors,
        )
        beam_number = parms.get("beam_number")
        if beam_number is None:
            errors.append(f"no beam_number {base}(300a,00c0)")
            continue

        _insert(db, "rt_beam", {"plan_id": plan_id}, _BEAM_PARAMS, parms)

        for spec in _SUB_TABLES:
            _sub_table(db, values, base, plan_id, beam_number, spec, errors)

        _general_accessories(db, values, base, plan_id, beam_number, errors)
        _control_points(db, values, base, plan_id, beam_number, errors)


def _insert(
    db: "Database",
    table: str,
    keys: dict[str, object],
    params: dict[str, str],
    parms: dict,
) -> None:
    """Insert one row: the key columns, then one column per parameter."""
    names = list(keys) + list(params)
    row = list(keys.values()) + [parms.get(name) for name in params]
    db.execute(
        f"insert into {table} ({', '.join(names)})"
        f" values ({', '.join(['%s'] * len(names))})",
        row,
    )


def _sub_table(
    db: "Database",
    values: ParsedValues,
    base: str,
    plan_id: object,
    beam_number: object,
    spec: SubTable,
    errors: list[str],
) -> None:
    pattern = f"{base}{spec.sequence}[<0>]{spec.key}"
    for (item,) in values.substitutions(pattern):
        prefix = f"{base}{spec.sequence}[{item}]"
        parms = get_attrs(
            values,
            {name: f"{prefix}{sig}" for name, sig in spec.params.items()},
            spec.coercions,
            errors,
        )
        missing = next(
            (name for name in spec.required if parms.get(name) is None), None
        )
        if missing is not None:
            errors.append(f"no {missing} {prefix}{spec.params[missing]}")
            continue
        _insert(
            db,
            spec.table,
            {"plan_id": plan_id, "beam_number": beam_number},
            spec.params,
            parms,
        )


def _general_accessories(
    db: "Database",
    values: ParsedValues,
    base: str,
    plan_id: object,
    beam_number: object,
    errors: list[str],
) -> None:
    """beam_general_accessory, whose INSERT is malformed in the Perl.

    The column list reads ``general_accessory_id text,`` -- a stray type
    name -- so the statement is a syntax error and the table never receives
    a row. Under DBI's default RaiseError=0 that prints and carries on.
    Reproduced by default; see posda.ingest.fixes.
    """
    spec = _GENERAL_ACCESSORY
    for (item,) in values.substitutions(f"{base}{spec.sequence}[<0>]{spec.key}"):
        prefix = f"{base}{spec.sequence}[{item}]"
        parms = get_attrs(
            values,
            {name: f"{prefix}{sig}" for name, sig in spec.params.items()},
            {},
            errors,
        )
        if parms.get("general_accessory_code") is None:
            errors.append(f"general accessory_code (beam {item}) undefined\n")
            continue
        if not fixes.ACTIVE.beam_general_accessory:
            continue
        _insert(
            db,
            spec.table,
            {"plan_id": plan_id, "beam_number": beam_number},
            spec.params,
            parms,
        )


def _control_points(
    db: "Database",
    values: ParsedValues,
    base: str,
    plan_id: object,
    beam_number: object,
    errors: list[str],
) -> None:
    sequence = "(300a,0111)"
    for (item,) in values.substitutions(f"{base}{sequence}[<0>](300a,0112)"):
        prefix = f"{base}{sequence}[{item}]"
        parms = get_attrs(
            values,
            {name: f"{prefix}{sig}" for name, sig in _CONTROL_POINT_PARAMS.items()},
            {
                "isocenter_position": "MultiText",
                "surface_entry_point": "MultiText",
            },
            errors,
        )
        index = parms.get("control_point_index")
        _insert(
            db,
            "beam_control_point",
            {"plan_id": plan_id, "beam_number": beam_number},
            _CONTROL_POINT_PARAMS,
            parms,
        )

        for spec in _CONTROL_POINT_SUB_TABLES:
            inner_pattern = f"{prefix}{spec.sequence}[<0>]{spec.key}"
            for (inner,) in values.substitutions(inner_pattern):
                inner_prefix = f"{prefix}{spec.sequence}[{inner}]"
                inner_parms = get_attrs(
                    values,
                    {name: f"{inner_prefix}{sig}" for name, sig in spec.params.items()},
                    spec.coercions,
                    errors,
                )
                columns = list(spec.params)
                names = ["plan_id", "beam_number", "control_point_index"] + columns
                db.execute(
                    f"insert into {spec.table} ({', '.join(names)})"
                    f" values ({', '.join(['%s'] * len(names))})",
                    [plan_id, beam_number, index]
                    + [inner_parms.get(c) for c in columns],
                )
