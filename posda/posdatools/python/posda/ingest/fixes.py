"""Opt-in corrections to defects the port reproduces by default.

The port is bug-for-bug so that it can be diff-verified against the Perl,
and that verification is what makes the cutover safe. Turning a fix on
necessarily breaks the equivalence, so every one of them is off by default
and should only be enabled *after* the Python workers have replaced the Perl
ones -- otherwise the two implementations disagree while both are live and
the differential harness stops being a useful signal.

Each flag is settable from the environment as ``POSDA_INGEST_FIX_<NAME>``,
accepting 1/true/yes. Enable them one at a time: several change row counts in
tables that analyst queries read.

Every defect here was confirmed against a real database, not inferred.

See ``docs/programming/Ingest-Fixes.md`` for the operator-facing version:
what each flag changes, which ones move row counts, and the migration
``lookup_upsert`` depends on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Fixes:
    """Which corrections are active."""

    #: Populate dicom_file.xfr_stx from the file meta transfer syntax.
    #: Posda::NewTry declares $xfr_stx and never assigns it, so the column is
    #: unconditionally NULL -- 0 of 1256 rows populated in the dev database.
    #: Safe: fills a column that is currently always NULL.
    xfr_stx: bool = False

    #: Populate file_sop_common.original_specialized_sop_class.
    #: DicomIod reads (0008,001b) into the key 'orig_spec_sop_class' but the
    #: insert passes $parms{original_specialized_sop_class}, which is never
    #: set. Confirmed: 0 of 1256 rows populated.
    #: Safe: fills a column that is currently always NULL.
    original_specialized_sop_class: bool = False

    #: Stop WindowLevel writing N^2 file_win_lev rows.
    #: The window-explanation branch nests two loops that both use $i; the
    #: inner shadows the outer, so the whole inner loop runs once per
    #: explanation. Only affects files that carry (0028,1055).
    #: CHANGES ROW COUNTS in file_win_lev.
    window_level_duplication: bool = False

    #: Parse without the 256-byte element limit.
    #: Posda::NewTry sets skip_large => 256, which silently NULLs any non-SQ
    #: value longer than that, and -- because it strips the pixel element's
    #: value -- also disables ImagePixel's deduplication entirely, leaving
    #: unique_pixel_data and pixel_location empty and creating a fresh image
    #: row per file. Both tables are empty in the dev database.
    #: COSTS MEMORY (pixel data is loaded) and CHANGES ROW COUNTS in image,
    #: unique_pixel_data and pixel_location.
    load_large_values: bool = False

    #: Walk ROIPhysicalPropertiesSequence (3006,00b0) when looking for
    #: elemental composition. RtRoiObservations walks (3006,00a0), the
    #: related-observations sequence, using the index from the physical
    #: properties loop, so roi_elemental_composition is effectively never
    #: populated.
    #: CHANGES ROW COUNTS in roi_elemental_composition.
    elemental_composition: bool = False

    #: Populate rt_dose.rt_dose_normalization_point. RTDose reads
    #: (3004,0008) into 'normalization_point' but passes
    #: $parms{normalizaton_point} to the insert -- missing an "i" -- so the
    #: column is unconditionally NULL.
    #: Safe: fills a column that is currently always NULL.
    dose_normalization_point: bool = False

    #: Read organ-at-risk maximum dose from (300a,002c) and the overdose
    #: volume fraction from (300a,002d). RtPrescription reads (300a,002b)
    #: into all three of limit dose, maximum dose and overdose fraction, so
    #: the last two carry the limit dose.
    #: CHANGES VALUES in rt_prescription_dose_ref.
    prescription_organ_at_risk_tags: bool = False

    #: Read fraction_related_dose's own UIDs. RtFractionScheme passes the
    #: fraction *group* parameter table to GetAttrs in that loop, so neither
    #: UID is read, both guards fire, and the table stays empty while two
    #: complaints are recorded per item.
    #: CHANGES ROW COUNTS in fraction_related_dose and
    #: dicom_process_errors.
    fraction_related_dose: bool = False

    #: Write beam_general_accessory rows. RtBeams' INSERT names the column
    #: 'general_accessory_id text', a stray type name that makes the
    #: statement a syntax error, so the table never receives a row.
    #: CHANGES ROW COUNTS in beam_general_accessory.
    beam_general_accessory: bool = False

    #: Use ON CONFLICT against the shared lookup tables instead of
    #: check-then-insert. Requires the unique indexes added by
    #: Posda/sql/migrations/ingest_lookup_unique.sql.
    #: Without it, concurrent workers race: 3 of 4 slope_intercept rows in
    #: the dev database are duplicates.
    #: REQUIRES A SCHEMA MIGRATION.
    lookup_upsert: bool = False

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Fixes":
        env = os.environ if environ is None else environ
        values = {}
        for spec in fields(cls):
            raw = env.get(f"POSDA_INGEST_FIX_{spec.name.upper()}")
            values[spec.name] = raw.strip().lower() in _TRUE if raw else False
        return cls(**values)

    @property
    def any_enabled(self) -> bool:
        return any(getattr(self, spec.name) for spec in fields(self))

    def enabled_names(self) -> list[str]:
        return [spec.name for spec in fields(self) if getattr(self, spec.name)]


#: Process-wide default, read once at import.
ACTIVE = Fixes.from_env()
