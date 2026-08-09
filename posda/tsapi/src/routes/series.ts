// Ports papi/routes/series.py.

import type { App, Ctx } from "../server";
import { doc, type OrEmpty } from "../openapi";
import { pathStr } from "../server";
import { HttpError, InternalError, jsonResponse } from "../httpx";
import type { Row } from "../db";
import { fetchJson, fetchOneJson, firstColumn } from "./common";

/**
 * A parsed "{series_instance_uid}", with optional "@{activity_id}" or
 * ":{activity_timepoint_id}" suffix — FastAPI expressed these as three
 * separate routes; here the suffix is parsed out of the path segment.
 */
export interface SeriesSpec {
  uid: string;
  activityId: number | null;
  timepointId: number | null;
}

export function parseSeriesSpec(spec: string): SeriesSpec {
  // '@' is checked first, matching the Python route registration order.
  const at = spec.lastIndexOf("@");
  if (at >= 0) {
    const id = spec.slice(at + 1);
    if (!/^-?\d+$/.test(id)) {
      throw new HttpError(422, "activity_id must be an integer");
    }
    return { uid: spec.slice(0, at), activityId: Number(id), timepointId: null };
  }
  const colon = spec.lastIndexOf(":");
  if (colon >= 0) {
    const id = spec.slice(colon + 1);
    if (!/^-?\d+$/.test(id)) {
      throw new HttpError(422, "activity_timepoint_id must be an integer");
    }
    return {
      uid: spec.slice(0, colon),
      activityId: null,
      timepointId: Number(id),
    };
  }
  return { uid: spec, activityId: null, timepointId: null };
}

/** GET /v1/series/{spec} */
export interface SeriesDetail {
  series_instance_uid: string;
  series_date: string | null;
  series_time: string | null;
  modality: string | null;
  laterality: string | null;
  series_description: string | null;
  file_count: number;
}

/** GET /v1/series/{spec}/frames elements. */
export interface SeriesFrame {
  file_id: number;
  frames: number;
}

/** GET /v1/series/{spec}/files */
export interface SeriesFileIDs {
  file_ids: number[];
}

/** An element of the timepoints list of GET /v1/series/{spec}/activities. */
export interface SeriesTimepoint {
  activity_id: number;
  activity_timepoint_id: number;
  when_created: string | null;
  creating_user: string | null;
}

/** GET /v1/series/{spec}/activities */
export interface SeriesActivities {
  activities: number[];
  timepoints: SeriesTimepoint[];
}

/** A row of the OHIF query, one per instance in the series. */
interface OhifRow {
  study_instance_uid: string | null;
  series_instance_uid: string | null;
  series_description: string | null;
  sop_instance_uid: string | null;
  file_id: number;
  pixel_columns: number | null;
  pixel_rows: number | null;
  bits_allocated: number | null;
  instance_number: string | null;
  image_type: string | null;
  samples_per_pixel: number | null;
  photometric_interpretation: string | null;
  bits_stored: number | null;
  high_bit: number | null;
  pixel_representation: number | null;
  pixel_spacing: string | null;
  iop: string | null;
  ipp: string | null;
  modality: string | null;
}

/**
 * DICOM attributes the Cornerstone viewer reads. Multi-valued
 * attributes are backslash-delimited in the database and are split into
 * arrays of strings here, not parsed into numbers.
 */
export interface OhifInstanceMetadata {
  Columns: number | null;
  Rows: number | null;
  InstanceNumber: string | null;
  PhotometricInterpretation: string | null;
  BitsAllocated: number | null;
  BitsStored: number | null;
  PixelRepresentation: number | null;
  SamplesPerPixel: number | null;
  PixelSpacing: string[];
  HighBit: number | null;
  ImageOrientationPatient: string[];
  ImagePositionPatient: string[];
  ImageType: string[];
  Modality: string | null;
  SOPInstanceUID: string | null;
  SeriesInstanceUID: string;
  StudyInstanceUID: string | null;
}

export interface OhifInstance {
  metadata: OhifInstanceMetadata;
  /** A "dicomweb:" URL pointing back at /v1/files/{file_id}/data. */
  url: string;
}

export interface OhifSeries {
  SeriesInstanceUID: string;
  SeriesDescription: string | null;
  instances: OhifInstance[];
}

export interface OhifStudy {
  StudyInstanceUID: string | null;
  series: OhifSeries[];
}

/** GET /v1/series/{spec}/ohif */
export interface OhifConfig {
  studies: OhifStudy[];
}

/** Shared description of the series selector these routes accept.
 * scripts/genopenapi.ts resolves module-level string constants. */
const SERIES_SPEC =
  "A SeriesInstanceUID, optionally suffixed with `@<activity_id>` or " +
  "`:<activity_timepoint_id>` to select the files as they were in that " +
  "activity or timepoint rather than the current ones.";

export function registerSeries(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "listing all series is not allowed");
  };
  app.prot("GET", "/v1/series", notAllowed,
    doc({
      summary: "Get All Studies",
    }),
  );
  app.prot("GET", "/v1/series/", notAllowed,
    doc({
      summary: "Get All Studies",
    }),
  );

  app.prot("GET", "/v1/series/:spec", (ctx) =>
    // The detail route never parses @/: suffixes (neither does FastAPI).
    fetchOneJson(
      app,
      `
      select distinct
          series_instance_uid,
          series_date,
          series_time::text,
          modality,
          laterality,
          series_description,
          count(file_id) as file_count
      from file_series
      where series_instance_uid = $1
      group by
          series_instance_uid,
          series_date,
          series_time,
          modality,
          laterality,
          series_description
      `,
      [pathStr(ctx, "spec")],
      { series_date: "date", file_count: "int8" },
    ),
    doc<OrEmpty<SeriesDetail>>({
      summary: "Get Series",
      description:
        "Details of a single series. Unlike the sub-resources below, this " +
        "route treats the whole path segment as a SeriesInstanceUID and " +
        "does not parse an @activity or :timepoint suffix.",
      params: { spec: { description: "A SeriesInstanceUID." } },
    }),
  );
  app.prot("GET", "/v1/series/:spec/ohif", (ctx) => getOhifConfig(app, ctx),
    doc<OhifConfig>({
      summary: "Get Ohif Config",
      description:
        "The OHIF/Cornerstone viewer configuration for the series, as a " +
        "JSON study descriptor with one displaySet per series.",
      params: { spec: { description: SERIES_SPEC } },
    }),
  );
  app.prot("GET", "/v1/series/:spec/frames", (ctx) => getSeriesFrames(app, ctx),
    doc<SeriesFrame[]>({
      summary: "Get Series Frames",
      description: "One entry per frame, ordered by slice position.",
      params: { spec: { description: SERIES_SPEC } },
    }),
  );
  app.prot("GET", "/v1/series/:spec/files", (ctx) => getSeriesFileIDs(app, ctx),
    doc<SeriesFileIDs>({
      summary: "Get Series Files",
      description: "The file_ids making up the series.",
      params: { spec: { description: SERIES_SPEC } },
    }),
  );
  app.prot("GET", "/v1/series/:spec/activities", (ctx) =>
    getSeriesActivities(app, ctx),
    doc<SeriesActivities>({
      summary: "Get Series Activities",
      description: "The activities this series appears in.",
      params: { spec: { description: SERIES_SPEC } },
    }),
  );
}

async function getOhifConfig(app: App, ctx: Ctx): Promise<Response> {
  const uid = pathStr(ctx, "spec");
  const rows = await app.db.fetch<OhifRow>(
    `
    select
        study_instance_uid,
        series_instance_uid,
        series_description,
        sop_instance_uid,
        file_id,
        pixel_columns,
        pixel_rows,
        bits_allocated,
        instance_number,
        image_type,
        samples_per_pixel,
        photometric_interpretation,
        bits_stored,
        high_bit,
        pixel_representation,
        pixel_spacing,
        iop,
        ipp,
        modality

    from file_series
    natural join file_study
    natural join file_sop_common
    natural join file_image
    natural join image
    natural join file_image_geometry
    natural join image_geometry
    where series_instance_uid = $1

    order by
        case instance_number
            when '' then '0'
            when null then '0'
            else instance_number
        end::int
    `,
    [uid],
  );
  if (rows.length === 0) {
    // Python indexes results[0] unconditionally and 500s on empty.
    throw new InternalError();
  }

  const dcmList = (v: string | null): string[] =>
    typeof v === "string" ? v.split("\\") : [];

  const instances: OhifInstance[] = rows.map((row) => ({
    metadata: {
      Columns: row.pixel_columns,
      Rows: row.pixel_rows,
      InstanceNumber: row.instance_number,
      PhotometricInterpretation: row.photometric_interpretation,
      BitsAllocated: row.bits_allocated,
      BitsStored: row.bits_stored,
      PixelRepresentation: row.pixel_representation,
      SamplesPerPixel: row.samples_per_pixel,
      PixelSpacing: dcmList(row.pixel_spacing),
      HighBit: row.high_bit,
      ImageOrientationPatient: dcmList(row.iop),
      ImagePositionPatient: dcmList(row.ipp),
      ImageType: dcmList(row.image_type),
      Modality: row.modality,
      SOPInstanceUID: row.sop_instance_uid,
      SeriesInstanceUID: uid,
      StudyInstanceUID: row.study_instance_uid,
    },
    url: `dicomweb:${app.cfg.apiUrl}/v1/files/${row.file_id}/data`,
  }));

  const config: OhifConfig = {
    studies: [
      {
        StudyInstanceUID: rows[0]!.study_instance_uid,
        series: [
          {
            SeriesInstanceUID: uid,
            SeriesDescription: rows[0]!.series_description,
            instances,
          },
        ],
      },
    ],
  };
  return jsonResponse(config);
}

const framesByTimepointQuery = `
    with timepoint_files as (
        select file_id
        from activity_timepoint_file
        where activity_timepoint_id = $2
    )
    select
        file_id,
        coalesce(number_of_frames, 1) as frames

    from
        timepoint_files
        natural join file_series
        natural join file_sop_common
        natural left join file_image
        natural left join image
    where series_instance_uid = $1
    order by
        -- sometimes instance_number is empty string or null
        case instance_number
            when '' then '0'
            when null then '0'
            else instance_number
        end::int
`;

async function getSeriesFrames(app: App, ctx: Ctx): Promise<Response> {
  const spec = parseSeriesSpec(pathStr(ctx, "spec"));

  if (spec.activityId !== null) {
    const row = await app.db.fetchOne(
      `
      select max(activity_timepoint_id)
      from activity_timepoint
      where activity_id = $1
      `,
      [spec.activityId],
    );
    return fetchJson(app, framesByTimepointQuery, [
      spec.uid,
      row?.max ?? null,
    ]);
  }
  if (spec.timepointId !== null) {
    return fetchJson(app, framesByTimepointQuery, [spec.uid, spec.timepointId]);
  }
  return fetchJson(
    app,
    `
    select
        file_id,
        coalesce(number_of_frames, 1) as frames

    from
        file_series
        natural join file_sop_common
        natural left join file_image
        natural left join image
    where series_instance_uid = $1
    order by
        -- sometimes instance_number is empty string or null
        case instance_number
            when '' then '0'
            when null then '0'
            else instance_number
        end::int
    `,
    [spec.uid],
  );
}

async function getSeriesFileIDs(app: App, ctx: Ctx): Promise<Response> {
  const spec = parseSeriesSpec(pathStr(ctx, "spec"));

  let rows: Row[];
  if (spec.timepointId !== null) {
    rows = await app.db.fetch(
      `
      with timepoint_files as (
          select file_id
          from activity_timepoint_file
          where activity_timepoint_id = $2
      )
      select file_id
      from
          timepoint_files
          natural join file_series
          natural join file_sop_common
      where series_instance_uid = $1
      order by
          case instance_number
              when '' then '0'
              when null then '0'
              else instance_number
          end::int
      `,
      [spec.uid, spec.timepointId],
    );
  } else if (spec.activityId !== null) {
    rows = await app.db.fetch(
      `
      with timepoint_files as (
          select file_id
          from activity_timepoint_file
          where
              activity_timepoint_id = (
                  select max(activity_timepoint_id)
                  from activity_timepoint
                  where activity_id = $2
              )
      )
      select file_id
      from
          timepoint_files
          natural join file_series
          natural join file_sop_common
      where series_instance_uid = $1
      order by
          case instance_number
              when '' then '0'
              when null then '0'
              else instance_number
          end::int
      `,
      [spec.uid, spec.activityId],
    );
  } else {
    rows = await app.db.fetch(
      `
      select file_id
      from
          file_series
          natural left join file_sop_common
          natural left join ctp_file
      where series_instance_uid = $1
      order by
          case instance_number
              when '' then '0'
              when null then '0'
              else instance_number
          end::int
      `,
      [spec.uid],
    );
  }

  return jsonResponse({ file_ids: firstColumn(rows) });
}

async function getSeriesActivities(app: App, ctx: Ctx): Promise<Response> {
  const uid = pathStr(ctx, "spec");

  const activities = await app.db.fetch(
    `
    select distinct
            activity_id
    from
        file_series
            natural join activity_timepoint_file
            natural join activity_timepoint
    where
        series_instance_uid = $1
    `,
    [uid],
  );

  // The response model serializes when_created via pydantic (naive
  // timestamps keep their plain isoformat).
  const timepoints = await app.db.fetch(
    `
    select distinct
            activity_id,
            activity_timepoint_id,
            when_created::text,
            creating_user
    from
        file_series
            natural join activity_timepoint_file
            natural join activity_timepoint
    where
        series_instance_uid = $1
    `,
    [uid],
    { when_created: "ts" },
  );

  return jsonResponse({
    activities: firstColumn(activities),
    timepoints,
  });
}
