"""Attribute tables transcribed from ``Posda::DB::Modules``.

Each Perl handler opens with a ``$..._parms`` hash mapping column name to
element signature and a ``$ModList`` hash naming the coercion to apply. Those
two tables are pure data, so they are lifted here verbatim; the handlers in
``modules.py`` supply only the INSERT that follows.

Signatures are kept in Posda's ``"(gggg,eeee)"`` string form rather than
converted to integers so that these tables can be diffed against the Perl by
eye during review.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AttrSpec:
    """One handler's ``$parms`` / ``$ModList`` pair."""

    params: dict[str, str]
    coercions: dict[str, str] = field(default_factory=dict)


PATIENT = AttrSpec(
    params={
        "dob": "(0010,0030)",
        "tob": "(0010,0032)",
        "other_ids": "(0008,1000)",
        "other_names": "(0008,1001)",
        "patient_name": "(0010,0010)",
        "patient_id": "(0010,0020)",
        "id_issuer": "(0010,0021)",
        "ethnic_group": "(0010,2160)",
        "comments": "(0010,4000)",
        "sex": "(0010,0040)",
        "patient_age": "(0010,1010)",
    },
    coercions={
        "dob": "Date",
        "tob": "Timetag",
        "other_ids": "MultiText",
        "other_names": "MultiText",
    },
)

STUDY = AttrSpec(
    params={
        "study_instance_uid": "(0020,000d)",
        "study_date": "(0008,0020)",
        "study_time": "(0008,0030)",
        "referring_phy_name": "(0008,0090)",
        "study_id": "(0020,0010)",
        "accession_number": "(0008,0050)",
        "study_description": "(0008,1030)",
        "phys_of_record": "(0008,1048)",
        "phys_reading": "(0008,1060)",
        "admitting_diag": "(0008,1080)",
    },
    coercions={
        "study_date": "Date",
        "study_time": "Timetag",
        "phys_of_record": "MultiText",
        "phys_reading": "MultiText",
        "admitting_diag": "MultiText",
    },
)

SERIES = AttrSpec(
    params={
        "modality": "(0008,0060)",
        "series_instance_uid": "(0020,000e)",
        "series_number": "(0020,0011)",
        "laterality": "(0020,0060)",
        "series_date": "(0008,0021)",
        "series_time": "(0008,0031)",
        "performing_phys": "(0008,1050)",
        "protocol_name": "(0018,1030)",
        "series_description": "(0008,103e)",
        "operators_name": "(0008,1070)",
        "body_part_examined": "(0018,0015)",
        "patient_position": "(0018,5100)",
        "smallest_pixel_value": "(0028,0108)",
        "largest_pixel_value": "(0028,0109)",
        "performed_procedure_step_id": "(0040,0253)",
        "performed_procedure_start_date": "(0040,0244)",
        "performed_procedure_start_time": "(0040,0245)",
        "performed_procedure_desc": "(0040,0254)",
        "performed_procedure_comments": "(0040,0280)",
    },
    coercions={
        "series_number": "UndefIfNotNumber",
        "series_date": "Date",
        "series_time": "Timetag",
        "performing_phys": "MultiText",
        "operators_name": "MultiText",
        "smallest_pixel_value": "UndefIfNotNumber",
        "largest_pixel_value": "UndefIfNotNumber",
        "performed_procedure_start_date": "Date",
        "performed_procedure_start_time": "Timetag",
    },
)

EQUIPMENT = AttrSpec(
    params={
        "manufacturer": "(0008,0070)",
        "institution_name": "(0008,0080)",
        "institution_addr": "(0008,0081)",
        "station_name": "(0008,1010)",
        "inst_dept_name": "(0008,1040)",
        "manuf_model_name": "(0008,1090)",
        "dev_serial_num": "(0018,1000)",
        "software_versions": "(0018,1020)",
        "spatial_resolution": "(0018,1050)",
        "last_calib_date": "(0018,1200)",
        "last_calib_time": "(0018,1201)",
        "pixel_pad": "(0028,0120)",
    },
    coercions={
        "software_versions": "MultiText",
        "last_calib_date": "MultiText",
        "last_calib_time": "MultiText",
    },
)

IMAGE_PIXEL = AttrSpec(
    params={
        "image_type": "(0008,0008)",
        "samples_per_pixel": "(0028,0002)",
        "pixel_spacing": "(0028,0030)",
        "photometric_interpretation": "(0028,0004)",
        "pixel_rows": "(0028,0010)",
        "pixel_columns": "(0028,0011)",
        "bits_allocated": "(0028,0100)",
        "bits_stored": "(0028,0101)",
        "high_bit": "(0028,0102)",
        "pixel_representation": "(0028,0103)",
        "planar_configuration": "(0028,0006)",
        "number_of_frames": "(0028,0008)",
        "content_date": "(0008,0023)",
        "content_time": "(0008,0033)",
    },
    coercions={
        "image_type": "MultiText",
        "pixel_spacing": "MultiText",
        "content_date": "Date",
        "content_time": "Timetag",
    },
)

IMAGE_PLANE = AttrSpec(
    params={
        "iop": "(0020,0037)",
        "ipp": "(0020,0032)",
        "for_uid": "(0020,0052)",
    },
    coercions={"iop": "MultiText", "ipp": "MultiText"},
)

FRAME_OF_REFERENCE = AttrSpec(
    params={
        "for_uid": "(0020,0052)",
        "position_ref_indicator": "(0020,1040)",
    }
)

CT_IMAGE = AttrSpec(
    params={
        "kvp": "(0018,0060)",
        "instance_number": "(0020,0013)",
        "scan_options": "(0018,0022)",
        "data_collection_diameter": "(0018,0090)",
        "reconstruction_diameter": "(0018,1100)",
        "dist_source_to_pat": "(0018,1111)",
        "dist_source_to_detect": "(0018,1110)",
        "gantry_tilt": "(0018,1120)",
        "rotation_dir": "(0018,1140)",
        "exposure_time": "(0018,1150)",
        "exposure": "(0018,1155)",
        "xray_tube_current": "(0018,1151)",
        "filter_type": "(0018,1160)",
        "generator_power": "(0018,1170)",
        "convolution_kernal": "(0018,1210)",
        "table_feed_per_rot": "(0018,9310)",
    },
    coercions={"scan_options": "MultiText", "convolution_kernal": "MultiText"},
)

# Attributes read directly by Posda::DB::DicomIod::Import, before any module
# handler runs.
SOP_COMMON = AttrSpec(
    params={
        "spec_char_set": "(0008,0005)",
        "sop_class": "(0008,0016)",
        "sop_instance": "(0008,0018)",
        "creation_date": "(0008,0012)",
        "creation_time": "(0008,0013)",
        "creator_uid": "(0008,0014)",
        "related_general_sop_class": "(0008,001a)",
        "orig_spec_sop_class": "(0008,001b)",
        "offset_from_utc": "(0008,0201)",
        "instance_number": "(0020,0013)",
        "instance_status": "(0100,0410)",
        "auth_date_time": "(0100,0420)",
        "auth_comment": "(0100,0424)",
        "auth_cert_num": "(0100,0426)",
    }
)

CTP = AttrSpec(
    params={
        "project_name": '(0013,"CTP",10)',
        "trial_name": '(0013,"CTP",11)',
        "site_name": '(0013,"CTP",12)',
        "site_id": '(0013,"CTP",13)',
        "file_visibility": '(0013,"CTP",14)',
        "batch": '(0013,"CTP",15)',
        "study_year": '(0013,"CTP",50)',
    }
)
