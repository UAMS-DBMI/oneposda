#!/usr/bin/python3 -u
ABOUT = """\
Runs the volume-geometry check query against the latest timepoint of an
activity and reports, for every DICOM series, whether it forms a
regularly-spaced rectilinear 3D volume that can be loaded directly into a
3D array without resampling.

Produces:
  * an email summary (total series, pass/fail/unknown counts, and a sample
    of the SeriesInstanceUIDs that failed the check), and
  * a CSV report named 'Volume Geometry' with one row per series and every
    individual geometry check column.

Expects nothing on STDIN.
"""

from posda.database import Database
from posda.background.process import BackgroundProcess

import argparse
import csv
from typing import Any, List, Tuple

# ---------------------------------------------------------------------------
# The volume-geometry check query, embedded so this script is self-contained.
#
# This is a raw string (r"""...""") on purpose: the query splits multi-valued
# DICOM attributes on the literal backslash delimiter (e.g.
# string_to_array(iop, '\')), and a normal Python string would swallow those
# backslashes.
#
# The single bind parameter is the activity_id (%s). See run_geometry_query()
# for why the other percent signs need escaping before execution.
# ---------------------------------------------------------------------------
QUERY = r"""
WITH
params AS (
  SELECT
    0.01::float8 AS relative_slice_tolerance, -- max allowed variation in slice spacing as a fraction
                                              -- of expected spacing (1%); matches the default
                                              -- _DEFAULT_SPACING_RELATIVE_TOLERANCE in highdicom
                                              -- (https://github.com/ImagingDataCommons/highdicom/blob/9750a6f9/src/highdicom/spatial.py#L19);
                                              -- relative tolerance scales correctly for both human
                                              -- imaging (~1-5mm spacing) and preclinical/small-animal
                                              -- imaging (~0.1mm spacing)
    0.1::float8  AS in_plane_tolerance,       -- max in-plane position jitter (mm)
    0.01::float8 AS orientation_tolerance,    -- cross-product magnitude deviation from 1.0
    %s as activity_id                         -- the activity to process
),

dicom_all AS (

  with activity_files as (
    select file_id
    from activity_timepoint_file
    where activity_timepoint_id = (
      select max(activity_timepoint_id)
      from activity_timepoint
      natural join params
    )
  )

  select
    series_instance_uid as SeriesInstanceUID,
    sop_class_uid as SOPClassUID,
    sop_instance_uid as SOPInstanceUID,
    modality as Modality,
    string_to_array(iop, '\') as ImageOrientationPatient,
    string_to_array(ipp, '\') as ImagePositionPatient,
    string_to_array(pixel_spacing, '\') as PixelSpacing,
    string_to_array(image_type, '\') as ImageType,
    pixel_rows as "Rows",
    pixel_columns as "Columns"

  from activity_files
  natural join file_sop_common
  natural join file_series
  natural join file_image
  natural join image
  natural join image_geometry

order by series_instance_uid
),

-- ---------------------------------------------------------------------------
-- CTE 1 -- rawData: extract per-instance geometry from DICOM headers
-- ---------------------------------------------------------------------------
-- Selects one row per DICOM instance (slice) for single-frame CT, MR, and PT
-- series, excluding localizer/scout images and MIP reconstructions.
-- Extracts the position (IPP), orientation vectors (IOP row and column
-- direction cosines), pixel spacing, and matrix dimensions for each instance.
rawData AS (
  SELECT
    SeriesInstanceUID,
    SOPInstanceUID,
    Modality,

    -- ImagePositionPatient (0020,0032): the x, y, z coordinates (in mm) of
    -- the upper-left corner of this slice in the patient coordinate system.
    ImagePositionPatient[1]::float8 AS ippX,
    ImagePositionPatient[2]::float8 AS ippY,
    ImagePositionPatient[3]::float8 AS ippZ,

    -- ImageOrientationPatient (0020,0037) as a single string for equality
    -- comparison -- if two instances have different IOP strings, the
    -- orientation changed within the series.
    array_to_string(ImageOrientationPatient, '/') AS iop,

    -- Row direction cosines: first 3 elements of IOP.
    -- This is the unit vector along the row (horizontal) direction of the
    -- image pixel grid in patient coordinates.
    (
      SELECT array_agg(part::float8 ORDER BY ord)
      FROM unnest(bid.ImageOrientationPatient) WITH ORDINALITY AS t(part, ord)
      WHERE ord BETWEEN 1 AND 3
    ) AS x_vector,

    -- Column direction cosines: last 3 elements of IOP.
    -- This is the unit vector along the column (vertical) direction of the
    -- image pixel grid in patient coordinates.
    (
      SELECT array_agg(part::float8 ORDER BY ord)
      FROM unnest(bid.ImageOrientationPatient) WITH ORDINALITY AS t(part, ord)
      WHERE ord BETWEEN 4 AND 6
    ) AS y_vector,

    -- PixelSpacing (0028,0030) as a string for equality comparison
    array_to_string(PixelSpacing, '/') AS pixelSpacing,

    -- Image matrix dimensions
    "Rows"    AS pixelRows,
    "Columns" AS pixelColumns

  FROM
    dicom_all bid
  WHERE
    -- Restrict to single-frame SOP Classes:
    --   1.2.840.10008.5.1.4.1.1.2   = CT Image Storage
    --   1.2.840.10008.5.1.4.1.1.4   = MR Image Storage
    --   1.2.840.10008.5.1.4.1.1.128 = Positron Emission Tomography Image Storage
    SOPClassUID IN ('1.2.840.10008.5.1.4.1.1.2', '1.2.840.10008.5.1.4.1.1.4', '1.2.840.10008.5.1.4.1.1.128')
    -- Exclude localizer (scout) images and MIP reconstructions, which are
    -- not part of the volumetric acquisition
    AND SeriesInstanceUID NOT IN (
      SELECT SeriesInstanceUID
      FROM dicom_all, unnest(ImageType) AS image_type
      WHERE image_type = 'LOCALIZER' OR image_type LIKE '%MIP%'
    )
),

-- ---------------------------------------------------------------------------
-- CTE 2 -- crossProduct: compute slice normal from orientation vectors
-- ---------------------------------------------------------------------------
-- The cross product of the row and column direction cosines gives the slice
-- normal vector. For a well-formed DICOM instance, the row and column vectors
-- are orthogonal unit vectors, so their cross product should also be a unit
-- vector (magnitude = 1.0). The cross product formula for vectors (a,b,c)
-- and (d,e,f) is: (bf-ce, cd-af, ae-bd).
-- PG has no STRUCT type, so we project the three components as plain columns.
crossProduct AS (
  SELECT
    SOPInstanceUID,
    SeriesInstanceUID,
    (x_vector[2] * y_vector[3] - x_vector[3] * y_vector[2]) AS cp_x,
    (x_vector[3] * y_vector[1] - x_vector[1] * y_vector[3]) AS cp_y,
    (x_vector[1] * y_vector[2] - x_vector[2] * y_vector[1]) AS cp_z
  FROM rawData
),

-- ---------------------------------------------------------------------------
-- CTE 3 -- sliceProjection: compute per-instance geometric coordinates
-- ---------------------------------------------------------------------------
-- For each instance, computes:
--   - crossProductMagnitude: length of the slice normal (should be ~1.0)
--   - slicePosition: the instance's position projected onto the slice normal
--     (a single scalar that represents "how far along the volume axis" this
--     slice is -- this works regardless of oblique orientation or gantry tilt)
--   - inPlaneRow/Col: the instance's position projected onto the row/column
--     directions (should be constant across all slices if they are aligned)
--   - slice_interval: distance to the next slice along the volume axis
--   - expected_spacing: the ideal uniform spacing computed from the full
--     span divided by (N-1), which is more numerically stable than comparing
--     adjacent pairs directly
sliceProjection AS (
  SELECT
    r.*,
    cp.cp_x,
    cp.cp_y,
    cp.cp_z,

    -- Magnitude of the cross product vector = sqrt(x^2 + y^2 + z^2).
    -- Should be ~1.0 for orthogonal unit vectors.
    sqrt(cp.cp_x * cp.cp_x + cp.cp_y * cp.cp_y + cp.cp_z * cp.cp_z) AS crossProductMagnitude,

    -- Dot product of IPP with the slice normal gives the scalar slice
    -- position along the volume axis.
    (r.ippX * cp.cp_x + r.ippY * cp.cp_y + r.ippZ * cp.cp_z) AS slicePosition,

    -- Dot product of IPP with the row direction. If all slices are aligned
    -- (no lateral shift), this value should be the same for every instance
    -- in the series.
    (r.ippX * r.x_vector[1] + r.ippY * r.x_vector[2] + r.ippZ * r.x_vector[3]) AS inPlaneRow,

    -- Dot product of IPP with the column direction (same logic as above).
    (r.ippX * r.y_vector[1] + r.ippY * r.y_vector[2] + r.ippZ * r.y_vector[3]) AS inPlaneCol,

    -- LEAD returns the slice position of the next instance when rows are
    -- sorted by slice position within each series. Subtracting the current
    -- position gives the spacing to the next slice. The last instance in
    -- each series gets NULL (no next slice).
    lead(r.ippX * cp.cp_x + r.ippY * cp.cp_y + r.ippZ * cp.cp_z)
      OVER (PARTITION BY r.SeriesInstanceUID
            ORDER BY (r.ippX * cp.cp_x + r.ippY * cp.cp_y + r.ippZ * cp.cp_z))
      - (r.ippX * cp.cp_x + r.ippY * cp.cp_y + r.ippZ * cp.cp_z) AS slice_interval,

    -- Expected uniform spacing = total span / (number of slices - 1).
    -- Derived from the first-to-last slice distance rather than any single
    -- adjacent pair, which minimizes floating-point accumulation errors.
    -- Reference: 3D Slicer acquisition geometry modeling
    -- (https://github.com/Slicer/Slicer/commit/3328b81211cb2e9ae16a0b49097744171c8c71c0).
    -- NULLIF avoids the divide-by-zero that would otherwise hit for a
    -- single-instance series where N-1 = 0 (matches BigQuery's SAFE_DIVIDE).
    (
      max(r.ippX * cp.cp_x + r.ippY * cp.cp_y + r.ippZ * cp.cp_z)
        OVER (PARTITION BY r.SeriesInstanceUID)
      - min(r.ippX * cp.cp_x + r.ippY * cp.cp_y + r.ippZ * cp.cp_z)
        OVER (PARTITION BY r.SeriesInstanceUID)
    ) / NULLIF(count(*) OVER (PARTITION BY r.SeriesInstanceUID) - 1, 0) AS expected_spacing

  FROM rawData r
  JOIN crossProduct cp USING (SOPInstanceUID, SeriesInstanceUID)
),

-- ---------------------------------------------------------------------------
-- CTE 4 -- geometryChecks: aggregate per-instance data into per-series checks
-- ---------------------------------------------------------------------------
-- Collapses all instances within each series into a single row with boolean
-- columns indicating whether each geometric property holds. Each check uses
-- aggregate functions (COUNT, MIN, MAX) across all instances in the series.
-- ANY_VALUE() is emulated with min() since per-series these values are
-- expected to be identical (see comments in the original BigQuery query).
geometryChecks AS (
  SELECT
    SeriesInstanceUID,
    min(Modality) AS Modality,

    -- single_orientation: TRUE if every instance has the same IOP string.
    -- Multiple orientations would mean the image plane rotated mid-series.
    count(DISTINCT iop) = 1 AS single_orientation,

    -- consistent_pixel_spacing: TRUE if every instance has the same
    -- PixelSpacing. Different spacings would mean the in-plane resolution
    -- changed mid-series.
    count(DISTINCT pixelSpacing) = 1 AS consistent_pixel_spacing,

    -- unique_slice_positions: TRUE if no two instances share the same
    -- projected slice position. Duplicate positions indicate overlapping
    -- slices (e.g., repeated acquisitions at the same location).
    count(DISTINCT SOPInstanceUID) = count(DISTINCT slicePosition) AS unique_slice_positions,

    -- consistent_image_dimensions: TRUE if all instances have the same
    -- Rows and Columns. Different dimensions would mean the pixel matrix
    -- size changed mid-series.
    count(DISTINCT pixelRows) = 1 AND count(DISTINCT pixelColumns) = 1 AS consistent_image_dimensions,

    -- orthogonal_orientation: TRUE if the cross product magnitude is ~1.0
    -- for all instances (within orientationTolerance). A magnitude far from
    -- 1.0 means the row and column direction cosines are not orthogonal
    -- unit vectors.
    (min(crossProductMagnitude) BETWEEN (1 - (SELECT orientation_tolerance FROM params))
                                    AND (1 + (SELECT orientation_tolerance FROM params)))
      AND
    (max(crossProductMagnitude) BETWEEN (1 - (SELECT orientation_tolerance FROM params))
                                    AND (1 + (SELECT orientation_tolerance FROM params)))
      AS orthogonal_orientation,

    -- consistent_in_plane_row: TRUE if the IPP projection onto the row
    -- direction varies by less than inPlaneTolerance across all instances.
    -- Large variation means slices are laterally shifted relative to each
    -- other (not stacked along a straight line).
    max(inPlaneRow) - min(inPlaneRow) < (SELECT in_plane_tolerance FROM params)
      AS consistent_in_plane_row,

    -- consistent_in_plane_col: same check for the column direction.
    max(inPlaneCol) - min(inPlaneCol) < (SELECT in_plane_tolerance FROM params)
      AS consistent_in_plane_col,

    -- uniform_slice_spacing: TRUE if every adjacent slice interval is
    -- within relativeSliceTolerance of the expected uniform spacing.
    -- The tolerance is relative (a fraction of expected_spacing) so it
    -- scales correctly for both human imaging (~1-5mm spacing) and
    -- preclinical/small-animal imaging (~0.1mm spacing).
    -- The expected spacing is derived from the full first-to-last span
    -- (see CTE 3 above). max() ignores NULLs, so the last slice (which has
    -- NULL slice_interval from LEAD) is automatically excluded.
    max(abs(slice_interval - expected_spacing))
      < (SELECT relative_slice_tolerance FROM params) * abs(min(expected_spacing))
      AS uniform_slice_spacing,

    -- obliquity_degrees: the angle (in degrees) between the slice normal
    -- and the nearest cardinal axis (X, Y, or Z in patient coordinates).
    -- 0 degrees means pure axial, sagittal, or coronal. Values > 0 indicate
    -- oblique acquisition or gantry tilt (e.g., ~15 degrees for tilted head CT).
    -- Computed as ACOS of the largest absolute component of the normalized
    -- slice normal vector -- the largest component corresponds to the
    -- nearest cardinal axis.
    round(
      (
        acos(
          least(1.0, greatest(
            abs(min(cp_x)),
            abs(min(cp_y)),
            abs(min(cp_z))
          ) / min(crossProductMagnitude))
        ) * 180 / pi()
      )::numeric,
      2
    ) AS obliquity_degrees

  FROM sliceProjection
  GROUP BY
    SeriesInstanceUID
)

-- ---------------------------------------------------------------------------
-- Final SELECT: output one row per series with all check results
-- ---------------------------------------------------------------------------
SELECT
  -- description:
  -- unique identifier of the DICOM series
  SeriesInstanceUID,
  -- description:
  -- TRUE if all instances share the same ImageOrientationPatient (DICOM attribute)
  single_orientation,
  -- description:
  -- TRUE if the cross product of row and column orientation vectors has unit magnitude
  -- (within orientationTolerance), confirming orthogonal direction cosines
  orthogonal_orientation,
  -- description:
  -- TRUE if every instance has a distinct slice position along the volume normal,
  -- i.e. no duplicate or overlapping slices
  unique_slice_positions,
  -- description:
  -- TRUE if the projection of ImagePositionPatient onto the row direction is constant
  -- across all instances (within inPlaneTolerance)
  consistent_in_plane_row,
  -- description:
  -- TRUE if the projection of ImagePositionPatient onto the column direction is constant
  -- across all instances (within inPlaneTolerance)
  consistent_in_plane_col,
  -- description:
  -- TRUE if all instances share the same PixelSpacing (DICOM attribute)
  consistent_pixel_spacing,
  -- description:
  -- TRUE if all instances share the same Rows and Columns values (DICOM attributes)
  consistent_image_dimensions,
  -- description:
  -- TRUE if the spacing between consecutive slices is constant
  -- (within relativeSliceTolerance, a relative fraction of expected spacing)
  uniform_slice_spacing,
  -- description:
  -- angle in degrees between the slice normal and the nearest cardinal axis
  -- (X, Y, or Z in patient coordinates); 0 means pure axial, sagittal, or coronal;
  -- values above 0 indicate oblique acquisition or gantry tilt
  obliquity_degrees,
  -- description:
  -- TRUE if all individual checks pass, indicating the series forms a regularly-spaced
  -- rectilinear 3D volume that can be loaded directly into a 3D array without resampling
  single_orientation AND orthogonal_orientation AND unique_slice_positions
    AND consistent_in_plane_row AND consistent_in_plane_col AND consistent_pixel_spacing
    AND consistent_image_dimensions AND uniform_slice_spacing AS regularly_spaced_3d_volume
FROM geometryChecks
ORDER BY regularly_spaced_3d_volume DESC NULLS LAST, SeriesInstanceUID
"""


def run_geometry_query(
    db: Database, activity_id: int
) -> Tuple[List[str], List[Any]]:
    """Run the embedded query and return (column names, rows).

    psycopg2 treats a bare '%' as the start of a bind placeholder, but the
    query legitimately contains literal percent signs (the LIKE '%MIP%'
    filter and a couple of comments). Doubling every '%' and then restoring
    the single real '%s' placeholder lets both coexist -- the same approach
    the original run_query.py used when it read the .sql file.
    """
    sql = QUERY.replace("%", "%%").replace("%%s", "%s")

    with db.cursor() as cur:
        cur.execute(sql, [activity_id])
        columns = [desc.name for desc in cur.description]
        rows = cur.fetchall()

    return columns, rows


def count_by_result(rows: List[Any]) -> Tuple[int, int, int]:
    """Return (pass, fail, unknown) counts for regularly_spaced_3d_volume."""
    true_count = sum(1 for r in rows if r.regularly_spaced_3d_volume is True)
    false_count = sum(1 for r in rows if r.regularly_spaced_3d_volume is False)
    unknown_count = len(rows) - true_count - false_count
    return true_count, false_count, unknown_count


def write_report(report_file, columns: List[str], rows: List[Any]) -> None:
    """Write every series and all of its check columns to a CSV report."""
    writer = csv.writer(report_file)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(list(row))


def print_summary(activity_id: int, rows: List[Any]) -> None:
    """Print the pass/fail summary and a sample of failing UIDs to the email."""
    total = len(rows)
    true_count, false_count, unknown_count = count_by_result(rows)
    false_pct = false_count / total * 100

    print(f"Activity ID : {activity_id}")
    print(f"Total series: {total}")
    print("Regularly Spaced 3D Volume?")
    print(f"  True      : {true_count}")
    print(f"  False     : {false_count}  ({false_pct:.1f}% of total)")
    if unknown_count:
        print(f"  NULL      : {unknown_count}")

    false_rows = [r for r in rows if r.regularly_spaced_3d_volume is False]
    if false_rows:
        print("\nFirst 10 series UIDs where regularly_spaced_3d_volume is False:")
        for r in false_rows[:10]:
            print(f"  {r.seriesinstanceuid}")


def main(args: argparse.Namespace) -> None:
    background = BackgroundProcess(
        args.background_id, args.notify, args.activity_id
    )
    background.daemonize()

    print(
        f"Checking volume geometry for the latest timepoint of "
        f"activity_id {args.activity_id}."
    )

    db = Database("posda_files")

    background.set_activity_status("Running volume geometry query")
    columns, rows = run_geometry_query(db, args.activity_id)

    if not rows:
        print(f"No series found for activity_id {args.activity_id}.")
        background.finish("Complete - no series found")
        return

    print_summary(args.activity_id, rows)

    report = background.create_report("Volume Geometry")
    write_report(report, columns, rows)

    background.finish("Complete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=ABOUT)
    parser.add_argument("background_id", help="the background_subprocess_id")
    parser.add_argument(
        "activity_id",
        type=int,
        help="the activity whose latest timepoint should be checked",
    )
    parser.add_argument("notify", help="user to notify when complete")

    return parser.parse_args()


if __name__ == "__main__":
    main(parse_args())
