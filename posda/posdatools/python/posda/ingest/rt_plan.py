"""RT Plan handlers, ported from ``Posda::DB::Modules``.

``RtPlan`` publishes ``plan_id``; every other handler in this module needs
it and gives up without one. They run in the order listed in the RT Plan
SOP class entry: RtPlan, RtPrescription, RtToleranceTables, RtPatientSetup,
RtFractionScheme, RtBeams, RtBrachy.

``RtPatientSetup`` is the one place this port deliberately departs from the
Perl rather than reproducing it -- see the note on that function.
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


def rt_plan(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RtPlan``: plan, file_plan and the two reference tables."""
    parms = get_attrs(
        values,
        {
            "plan_label": "(300a,0002)",
            "plan_name": "(300a,0003)",
            "plan_description": "(300a,0004)",
            "instance_number": "(0020,0013)",
            "operators_name": "(0008,1070)",
            "rt_plan_date": "(300a,0006)",
            "rt_plan_time": "(300a,0007)",
            "rt_treatment_protocols": "(300a,0009)",
            "plan_intent": "(300a,000a)",
            "treatment_sites": "(300a,000b)",
            "rt_plan_geometry": "(300a,000c)",
            "ss_referenced_from_plan": "(300c,0060)[0](0008,1155)",
        },
        {
            "rt_plan_date": "Date",
            "rt_plan_time": "Timetag",
            "rt_treatment_protocols": "MultiText",
            "operators_name": "MultiText",
            "treatment_sites": "MultiText",
        },
        errors,
    )
    if parms.get("plan_label") is None:
        errors.append("plan label undefined")
        return
    if parms.get("rt_plan_geometry") is None:
        errors.append("plan geometry undefined")
        return

    plan_id = db.insert_returning(
        "insert into plan"
        " (plan_label, plan_name, plan_description, instance_number,"
        "  operators_name, rt_plan_date, rt_plan_time,"
        "  rt_treatment_protocols, plan_intent, treatment_sites,"
        "  rt_plan_geometry, ss_referenced_from_plan)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            parms.get("plan_label"),
            parms.get("plan_name"),
            parms.get("plan_description"),
            parms.get("instance_number"),
            parms.get("operators_name"),
            parms.get("rt_plan_date"),
            parms.get("rt_plan_time"),
            parms.get("rt_treatment_protocols"),
            parms.get("plan_intent"),
            parms.get("treatment_sites"),
            parms.get("rt_plan_geometry"),
            parms.get("ss_referenced_from_plan"),
        ],
        "plan_id",
    )
    if not plan_id:
        errors.append("unable to get plan_id")
        return
    hist["plan_id"] = plan_id

    db.execute(
        "insert into file_plan (plan_id, file_id) values (%s, %s)",
        [plan_id, file_id],
    )

    for (item,) in values.substitutions("(300c,0080)[<0>](0008,1155)"):
        db.execute(
            "insert into dose_referenced_from_plan"
            " (plan_id, dose_sop_instance_uid) values (%s, %s)",
            [plan_id, values.get(f"(300c,0080)[{item}](0008,1155)")],
        )

    for (item,) in values.substitutions("(300c,0002)[<0>](0008,1155)"):
        base = f"(300c,0002)[{item}]"
        db.execute(
            "insert into plan_related_plans"
            " (plan_id, related_plan_instance_uid, plan_relationship)"
            " values (%s, %s, %s)",
            [
                plan_id,
                values.get(f"{base}(0008,1155)"),
                values.get(f"{base}(300a,0055)"),
            ],
        )


def rt_prescription(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RtPrescription``."""
    parms = get_attrs(values, {"rt_prescription_desc": "(300a,000e)"}, {}, errors)
    if not hist.get("plan_id"):
        errors.append("no plan (RtPrescription module)")
        return

    presc_id = db.insert_returning(
        "insert into rt_prescription (plan_id, rt_prescription_description)"
        " values (%s, %s)",
        [hist["plan_id"], parms.get("rt_prescription_desc")],
        "rt_prescription_id",
    )
    if not presc_id:
        errors.append("unable to get presc_id")
        return

    for (item,) in values.substitutions("(300a,0010)[<0>](300a,0012)"):
        base = f"(300a,0010)[{item}]"
        # The Perl reads (300a,002b) into organ_at_risk_limit_dose,
        # organ_at_risk_maximum_dose and organ_at_overdose_volume_fraction
        # alike, so the last two carry the limit dose. Reproduced by
        # default; see posda.ingest.fixes.
        if fixes.ACTIVE.prescription_organ_at_risk_tags:
            maximum_tag, overdose_tag = "(300a,002c)", "(300a,002d)"
        else:
            maximum_tag, overdose_tag = "(300a,002b)", "(300a,002b)"
        parms = get_attrs(
            values,
            {
                "dose_reference_number": f"{base}(300a,0012)",
                "dose_reference_uid": f"{base}(300a,0013)",
                "referenced_roi_number": f"{base}(300a,0084)",
                "dose_reference_point": f"{base}(300a,0018)",
                "nominal_prior_dose": f"{base}(300a,001a)",
                "dose_reference_structure_type": f"{base}(300a,0014)",
                "dose_reference_description": f"{base}(300a,0016)",
                "dose_reference_type": f"{base}(300a,0020)",
                "constraint_weight": f"{base}(300a,0021)",
                "delivery_warning_dose": f"{base}(300a,0022)",
                "delivery_maximum_dose": f"{base}(300a,0023)",
                "target_minimum_dose": f"{base}(300a,0025)",
                "target_prescription_dose": f"{base}(300a,0026)",
                "target_maximum_dose": f"{base}(300a,0027)",
                "target_underdose_volume_fraction": f"{base}(300a,0028)",
                "organ_at_risk_full_volume_dose": f"{base}(300a,002a)",
                "organ_at_risk_limit_dose": f"{base}(300a,002b)",
                "organ_at_risk_maximum_dose": f"{base}{maximum_tag}",
                "organ_at_overdose_volume_fraction": f"{base}{overdose_tag}",
            },
            {"dose_reference_point": "MultiText"},
            errors,
        )
        if parms.get("dose_reference_number") is None:
            errors.append("dose reference missing dose_reference_number")
            continue
        # The Perl also guards on dose_reference_structure_type and
        # dose_reference_type, but with `exists` rather than `defined`, and
        # GetAttrs always creates the key -- so neither guard can fire.
        db.execute(
            "insert into rt_prescription_dose_ref"
            " (rt_prescription_id, dose_reference_number, dose_reference_uid,"
            "  referenced_roi_number, dose_reference_point,"
            "  nominal_prior_dose, dose_reference_structure_type,"
            "  dose_reference_type, constraint_weight, delivery_warning_dose,"
            "  delivery_maximum_dose, target_minimum_dose,"
            "  target_prescription_dose, target_maximum_dose,"
            "  target_underdose_volume_fraction,"
            "  organ_at_risk_full_volume_dose, organ_at_risk_limit_dose,"
            "  organ_at_risk_maximum_dose, organ_at_overdose_volume_fraction)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
            "         %s, %s, %s, %s, %s, %s)",
            [presc_id]
            + [
                parms.get(name)
                for name in (
                    "dose_reference_number",
                    "dose_reference_uid",
                    "referenced_roi_number",
                    "dose_reference_point",
                    "nominal_prior_dose",
                    "dose_reference_structure_type",
                    "dose_reference_type",
                    "constraint_weight",
                    "delivery_warning_dose",
                    "delivery_maximum_dose",
                    "target_minimum_dose",
                    "target_prescription_dose",
                    "target_maximum_dose",
                    "target_underdose_volume_fraction",
                    "organ_at_risk_full_volume_dose",
                    "organ_at_risk_limit_dose",
                    "organ_at_risk_maximum_dose",
                    "organ_at_overdose_volume_fraction",
                )
            ],
        )


_TOLERANCE_COLUMNS = (
    ("tolerance_table_number", "(300a,0042)"),
    ("tolerance_table_label", "(300a,0043)"),
    ("gantry_angle_tolerance", "(300a,0044)"),
    ("gantry_angle_pitch_tolerance", "(300a,014e)"),
    ("beam_limiting_device_angle_tolerance", "(300a,0046)"),
    ("patient_support_angle_tolerance", "(300a,004c)"),
    ("table_top_eccentric_angle_tolerance", "(300a,004e)"),
    ("table_top_pitch_angle_tolerance", "(300a,004f)"),
    ("table_top_roll_angle_tolerance", "(300a,0050)"),
    ("table_top_vert_pos_tolerance", "(300a,0051)"),
    ("table_top_log_pos_tolerance", "(300a,0052)"),
    ("table_top_lat_pos_tolerance", "(300a,0053)"),
)


def rt_tolerance_tables(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RtToleranceTables``."""
    for (item,) in values.substitutions("(300a,0040)[<0>](300a,0042)"):
        base = f"(300a,0040)[{item}]"
        parms = get_attrs(
            values,
            {name: f"{base}{sig}" for name, sig in _TOLERANCE_COLUMNS},
            {},
            errors,
        )
        table_number = parms.get("tolerance_table_number")
        if not table_number:
            errors.append(f"no tolerance_table_number in item {item}")
            continue

        db.execute(
            "insert into rt_beam_tolerance_table (plan_id, "
            + ", ".join(name for name, _ in _TOLERANCE_COLUMNS)
            + ") values ("
            + ", ".join(["%s"] * (len(_TOLERANCE_COLUMNS) + 1))
            + ")",
            [hist.get("plan_id")] + [parms.get(name) for name, _ in _TOLERANCE_COLUMNS],
        )

        for (device,) in values.substitutions(f"{base}(300a,0048)[<0>](300a,00b8)"):
            limit = f"{base}(300a,0048)[{device}]"
            device_parms = get_attrs(
                values,
                {
                    "beam_limit_dev_type": f"{limit}(300a,00b8)",
                    "beam_limit_dev_pos_tolerance": f"{limit}(300a,004a)",
                },
                {},
                errors,
            )
            db.execute(
                "insert into rt_beam_limit_dev_tolerance"
                " (plan_id, tolerance_table_number, beam_limit_dev_type,"
                "  beam_limit_dev_pos_tolerance) values (%s, %s, %s, %s)",
                [
                    hist.get("plan_id"),
                    table_number,
                    device_parms.get("beam_limit_dev_type"),
                    device_parms.get("beam_limit_dev_pos_tolerance"),
                ],
            )


def rt_patient_setup(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Corrected port of ``RtPatientSetup``.

    This is the one handler the port does *not* reproduce faithfully,
    because what it reproduces would be a crash. The Perl:

    - calls ``$ds->prepare(...)`` on a Posda::Dataset for the fixation
      device insert (Modules.pm:1697). There is no such method, so any
      patient setup carrying a FixationDeviceSequence dies. Handlers run
      without eval, so the whole file import dies with it, leaving whatever
      rows had already been written under autocommit and skipping
      RtFractionScheme and RtBeams entirely.
    - writes to ``rt_plan_fixation_device``; the table is really
      ``rt_plan_setup_fixation_device``.
    - builds its fixation device signatures as ``(300a,0190[$j]`` -- a
      missing paren, which would fail signature parsing.
    - nests the shielding device, setup device and respiratory motion loops
      *inside* the setup-image loop, so those rows appear once per setup
      image and not at all when there is none.

    All four are fixed here. Where a plan has exactly one setup image and no
    fixation devices, this still agrees row-for-row with the Perl, which is
    what the differential corpus exercises.
    """
    for (item,) in values.substitutions("(300a,0180)[<0>](300a,0182)"):
        base = f"(300a,0180)[{item}]"
        parms = get_attrs(
            values,
            {
                "patient_setup_num": f"{base}(300a,0182)",
                "patient_setup_label": f"{base}(300a,0183)",
                "patient_position": f"{base}(0018,5100)",
                "patient_addl_pos": f"{base}(300a,0184)",
                "setup_technique": f"{base}(300a,01b0)",
                "setup_technique_description": f"{base}(300a,01b2)",
                "table_top_vert_disp": f"{base}(300a,01d2)",
                "table_top_long_disp": f"{base}(300a,01d4)",
                "table_top_lat_disp": f"{base}(300a,01d6)",
            },
            {},
            errors,
        )
        setup_num = parms.get("patient_setup_num")
        if not setup_num:
            errors.append(f"no patient_setup {item}")
            continue

        plan_id = hist.get("plan_id")
        db.execute(
            "insert into rt_plan_patient_setup"
            " (plan_id, patient_setup_num, patient_setup_label,"
            "  patient_position, patient_addl_pos, setup_technique,"
            "  setup_technique_description, table_top_vert_disp,"
            "  table_top_long_disp, table_top_lat_disp)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [plan_id]
            + [
                parms.get(name)
                for name in (
                    "patient_setup_num",
                    "patient_setup_label",
                    "patient_position",
                    "patient_addl_pos",
                    "setup_technique",
                    "setup_technique_description",
                    "table_top_vert_disp",
                    "table_top_long_disp",
                    "table_top_lat_disp",
                )
            ],
        )

        _setup_images(db, values, base, plan_id, setup_num, errors)
        _fixation_devices(db, values, base, plan_id, setup_num, errors)
        _shielding_devices(db, values, base, plan_id, setup_num, errors)
        _setup_devices(db, values, base, plan_id, setup_num, errors)
        _respiratory_motion(db, values, base, plan_id, setup_num, errors)


def _setup_images(db, values, base, plan_id, setup_num, errors) -> None:
    for (item,) in values.substitutions(f"{base}(300a,0401)[<0>](0008,1155)"):
        image = f"{base}(300a,0401)[{item}]"
        parms = get_attrs(
            values,
            {
                "setup_image_comment": f"{image}(300a,0402)",
                "image_sop_class_uid": f"{image}(0008,1150)",
                "image_sop_instance_uid": f"{image}(0008,1155)",
            },
            {},
            errors,
        )
        db.execute(
            "insert into rt_plan_setup_image"
            " (plan_id, patient_setup_num, setup_image_comment,"
            "  image_sop_class_uid, image_sop_instance_uid)"
            " values (%s, %s, %s, %s, %s)",
            [
                plan_id,
                setup_num,
                parms.get("setup_image_comment"),
                parms.get("image_sop_class_uid"),
                parms.get("image_sop_instance_uid"),
            ],
        )


def _fixation_devices(db, values, base, plan_id, setup_num, errors) -> None:
    for (item,) in values.substitutions(f"{base}(300a,0190)[<0>](300a,0192)"):
        device = f"{base}(300a,0190)[{item}]"
        parms = get_attrs(
            values,
            {
                "fixation_device_type": f"{device}(300a,0192)",
                "fixaction_device_label": f"{device}(300a,0194)",
                "fixation_device_description": f"{device}(300a,0196)",
                "fixation_device_position": f"{device}(300a,0198)",
                "fixation_device_pitch_angle": f"{device}(300a,0199)",
                "fixation_device_roll_angle": f"{device}(300a,019a)",
                "fixation_device_accessory_code": f"{device}(300a,01f9)",
            },
            {},
            errors,
        )
        # Both the table and the label column carry typos in the schema.
        db.execute(
            "insert into rt_plan_setup_fixation_device"
            " (plan_id, patient_setup_num, fixation_device_type,"
            "  fixaction_device_label, fixation_device_description,"
            "  fixation_device_position, fixation_device_pitch_angle,"
            "  fixation_device_roll_angle, fixation_device_accessory_code)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [plan_id, setup_num]
            + [
                parms.get(name)
                for name in (
                    "fixation_device_type",
                    "fixaction_device_label",
                    "fixation_device_description",
                    "fixation_device_position",
                    "fixation_device_pitch_angle",
                    "fixation_device_roll_angle",
                    "fixation_device_accessory_code",
                )
            ],
        )


def _shielding_devices(db, values, base, plan_id, setup_num, errors) -> None:
    for (item,) in values.substitutions(f"{base}(300a,01a0)[<0>](300a,01a2)"):
        device = f"{base}(300a,01a0)[{item}]"
        parms = get_attrs(
            values,
            {
                "shielding_device_type": f"{device}(300a,01a2)",
                "shielding_device_label": f"{device}(300a,01a4)",
                "shielding_device_description": f"{device}(300a,01a6)",
                "shielding_device_accessory_code": f"{device}(300a,01a8)",
            },
            {},
            errors,
        )
        db.execute(
            "insert into rt_plan_setup_shielding_device"
            " (plan_id, patient_setup_num, shielding_device_type,"
            "  shielding_device_label, shielding_device_description,"
            "  shielding_device_accessory_code)"
            " values (%s, %s, %s, %s, %s, %s)",
            [plan_id, setup_num]
            + [
                parms.get(name)
                for name in (
                    "shielding_device_type",
                    "shielding_device_label",
                    "shielding_device_description",
                    "shielding_device_accessory_code",
                )
            ],
        )


def _setup_devices(db, values, base, plan_id, setup_num, errors) -> None:
    for (item,) in values.substitutions(f"{base}(300a,01b4)[<0>](300a,01b6)"):
        device = f"{base}(300a,01b4)[{item}]"
        parms = get_attrs(
            values,
            {
                "setup_device_type": f"{device}(300a,01b6)",
                "setup_device_label": f"{device}(300a,01b8)",
                # The Perl writes (300a,1b4) here, dropping a digit, so the
                # description never reads. Corrected along with the rest of
                # this handler.
                "setup_device_description": f"{device}(300a,01ba)",
                "setup_device_parameter": f"{device}(300a,01bc)",
                "setup_reference_description": f"{device}(300a,01d0)",
            },
            {},
            errors,
        )
        db.execute(
            "insert into rt_plan_setup_device"
            " (plan_id, patient_setup_num, setup_device_type,"
            "  setup_device_label, setup_device_description,"
            "  setup_device_parameter, setup_reference_description)"
            " values (%s, %s, %s, %s, %s, %s, %s)",
            [plan_id, setup_num]
            + [
                parms.get(name)
                for name in (
                    "setup_device_type",
                    "setup_device_label",
                    "setup_device_description",
                    "setup_device_parameter",
                    "setup_reference_description",
                )
            ],
        )


def _respiratory_motion(db, values, base, plan_id, setup_num, errors) -> None:
    for (item,) in values.substitutions(f"{base}(300a,0410)[<0>](0018,9170)"):
        motion = f"{base}(300a,0410)[{item}]"
        parms = get_attrs(
            values,
            {
                "respiratory_motion_comp_technique": f"{motion}(0018,9170)",
                "respiratory_signal_source": f"{motion}(0018,9171)",
                "respiratory_motion_com_tech_desc": f"{motion}(0018,9185)",
                "respiratory_signal_source_id": f"{motion}(0018,9186)",
            },
            {},
            errors,
        )
        db.execute(
            "insert into rt_plan_respiratory_motion_comp"
            " (plan_id, patient_setup_num, sequence_index,"
            "  respiratory_motion_comp_technique, respiratory_signal_source,"
            "  respiratory_motion_com_tech_desc, respiratory_signal_source_id)"
            " values (%s, %s, %s, %s, %s, %s, %s)",
            [plan_id, setup_num, item]
            + [
                parms.get(name)
                for name in (
                    "respiratory_motion_comp_technique",
                    "respiratory_signal_source",
                    "respiratory_motion_com_tech_desc",
                    "respiratory_signal_source_id",
                )
            ],
        )


_FRACTION_DOSE_COLUMNS = (
    ("dose_reference_number", "(300c,0051)"),
    ("constraint_weight", "(300a,0021)"),
    ("delivery_warning_dose", "(300a,0022)"),
    ("delivery_maximum_dose", "(300a,0023)"),
    ("target_minimum_dose", "(300a,0025)"),
    ("target_prescription_dose", "(300a,0026)"),
    ("target_maximum_dose", "(300a,0027)"),
    ("target_underdose_volume_fraction", "(300a,0028)"),
    ("organ_at_risk_full_volume_dose", "(300a,002a)"),
    ("organ_at_risk_limit_dose", "(300a,002b)"),
    ("organ_at_risk_maximum_dose", "(300a,002c)"),
    ("organ_at_risk_overdose_volume_fraction", "(300a,002d)"),
)

_FRACTION_BEAM_COLUMNS = (
    ("beam_number", "(300c,0006)"),
    ("beam_dose_specification_point", "(300a,0082)"),
    ("beam_dose", "(300a,0084)"),
    ("beam_dose_point_depth", "(300a,0088)"),
    ("beam_dose_point_equivalent_depth", "(300a,0089)"),
    ("beam_dose_point_ssd", "(300a,008a)"),
    ("beam_meterset", "(300a,0086)"),
)


def rt_fraction_scheme(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    hist: dict,
    errors: list[str],
) -> None:
    """Port of ``RtFractionScheme``."""
    plan_id = hist.get("plan_id")
    for (item,) in values.substitutions("(300a,0070)[<0>](300a,0071)"):
        base = f"(300a,0070)[{item}]"
        group_params = {
            "fraction_group_number": f"{base}(300a,0071)",
            "fraction_group_descripton": f"{base}(300a,0072)",
            "number_of_fractions_planned": f"{base}(300a,0078)",
            "number_of_fraction_digits_per_day": f"{base}(300a,0079)",
            "repeat_fraction_cycle_length": f"{base}(300a,007a)",
            "fraction_pattern": f"{base}(300a,007b)",
            "number_of_beams": f"{base}(300a,0080)",
            "number_of_brachy_application_setups": f"{base}(300a,00a0)",
        }
        parms = get_attrs(
            values,
            group_params,
            {"number_of_fractions_planned": "Integer"},
            errors,
        )
        group_number = parms.get("fraction_group_number")
        if group_number is None:
            errors.append(f"Undefined fraction group number {base}(300a,0071)")
            continue

        db.execute(
            "insert into rt_plan_fraction_group"
            " (plan_id, fraction_group_number, fraction_group_descripton,"
            "  number_of_fractions_planned,"
            "  number_of_fraction_digits_per_day,"
            "  repeat_fraction_cycle_length, fraction_pattern,"
            "  number_of_beams, number_of_brachy_application_setups)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [plan_id]
            + [
                parms.get(name)
                for name in (
                    "fraction_group_number",
                    "fraction_group_descripton",
                    "number_of_fractions_planned",
                    "number_of_fraction_digits_per_day",
                    "repeat_fraction_cycle_length",
                    "fraction_pattern",
                    "number_of_beams",
                    "number_of_brachy_application_setups",
                )
            ],
        )

        _fraction_related_dose(
            db, values, base, plan_id, group_number, group_params, errors
        )
        _fraction_reference_dose(db, values, base, plan_id, group_number, errors)
        _fraction_reference_beam(db, values, base, plan_id, group_number, errors)

        for _ in values.substitutions(f"{base}(300c,000a)[<0>](300c,000c)"):
            errors.append("yikes - brachy references not yet implemented")


def _fraction_related_dose(
    db, values, base, plan_id, group_number, group_params, errors
) -> None:
    for (item,) in values.substitutions(f"{base}(300c,0080)[<0>](0008,1155)"):
        dose = f"{base}(300c,0080)[{item}]"
        own_params = {
            "sop_class_uid": f"{dose}(0008,1150)",
            "sop_instance_uid": f"{dose}(0008,1155)",
        }
        # The Perl passes the *fraction group* parameter table to GetAttrs
        # here instead of this one, so neither UID is ever read, both guards
        # fire and the table stays empty. Reproduced by default; see
        # posda.ingest.fixes.
        used = own_params if fixes.ACTIVE.fraction_related_dose else group_params
        parms = get_attrs(values, used, {}, errors)
        if parms.get("sop_instance_uid") is None:
            errors.append(f"undefined sop_instance_uid: {dose}(0008,1155)")
            continue
        if parms.get("sop_class_uid") is None:
            errors.append(f"undefined sop_class_uid: {dose}(0008,1150)")
            continue
        db.execute(
            "insert into fraction_related_dose"
            " (plan_id, fraction_group_number, sop_class_uid,"
            "  sop_instance_uid) values (%s, %s, %s, %s)",
            [
                plan_id,
                group_number,
                parms.get("sop_class_uid"),
                parms.get("sop_instance_uid"),
            ],
        )


def _fraction_reference_dose(db, values, base, plan_id, group_number, errors) -> None:
    for (item,) in values.substitutions(f"{base}(300c,0050)[<0>](300c,0051)"):
        dose = f"{base}(300c,0050)[{item}]"
        parms = get_attrs(
            values,
            {name: f"{dose}{sig}" for name, sig in _FRACTION_DOSE_COLUMNS},
            {},
            errors,
        )
        if parms.get("dose_reference_number") is None:
            errors.append(f"undefined dose_reference_number: {dose}(300c,0051)")
            continue
        db.execute(
            "insert into fraction_reference_dose"
            " (plan_id, fraction_group_number, "
            + ", ".join(name for name, _ in _FRACTION_DOSE_COLUMNS)
            + ") values ("
            + ", ".join(["%s"] * (len(_FRACTION_DOSE_COLUMNS) + 2))
            + ")",
            [plan_id, group_number]
            + [parms.get(name) for name, _ in _FRACTION_DOSE_COLUMNS],
        )


def _fraction_reference_beam(db, values, base, plan_id, group_number, errors) -> None:
    for (item,) in values.substitutions(f"{base}(300c,0004)[<0>](300c,0006)"):
        beam = f"{base}(300c,0004)[{item}]"
        parms = get_attrs(
            values,
            {name: f"{beam}{sig}" for name, sig in _FRACTION_BEAM_COLUMNS},
            {"beam_dose_specification_point": "MultiText"},
            errors,
        )
        if parms.get("beam_number") is None:
            errors.append(f"Undefined beam number: {beam}(300c,0006)")
            continue
        db.execute(
            "insert into fraction_reference_beam"
            " (plan_id, fraction_group_number, "
            + ", ".join(name for name, _ in _FRACTION_BEAM_COLUMNS)
            + ") values ("
            + ", ".join(["%s"] * (len(_FRACTION_BEAM_COLUMNS) + 2))
            + ")",
            [plan_id, group_number]
            + [parms.get(name) for name, _ in _FRACTION_BEAM_COLUMNS],
        )
