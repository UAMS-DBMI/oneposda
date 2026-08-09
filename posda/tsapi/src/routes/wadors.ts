// Ports papi/routes/wadors.py: the minimal WADO-RS subset used by the
// Cornerstone viewer.

import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathStr } from "../server";
import { HttpError, InternalError, errNoRecords, jsonResponse } from "../httpx";
import type { Row } from "../db";
import { readFileFrom } from "./common";

interface WadorsValue {
  Value: unknown[];
  vr: string;
}

/** The study selector accepted in place of a StudyInstanceUID. */
const WADORS_STUDY =
  "A study selector of the form `iec:<iec>`, `timepoint:<timepoint_id>` " +
  "or `activity:<activity_id>` — Posda addresses studies by these rather " +
  "than by StudyInstanceUID.";

export function registerWadoRS(app: App): void {
  app.prot(
    "GET",
    "/v1/wadors/studies/:study/series/:series/instances/:sop/frames/:frame",
    (ctx) => wadorsFrames(app, ctx),
    doc({
      summary: "Retrieve Frames",
      description:
        "WADO-RS frame retrieval: the raw pixel data of a single frame, " +
        "as a multipart/related part.",
      params: {
        study: { description: WADORS_STUDY },
        series: { description: "A SeriesInstanceUID." },
        sop: { description: "An SOPInstanceUID." },
        frame: { type: "integer", description: "1-based frame number." },
      },
      produces: "multipart/related",
    }),
  );
  app.prot("GET", "/v1/wadors/studies/:study/series/:series/metadata", (ctx) =>
    wadorsMetadata(app, ctx),
    doc({
      summary: "Retrieve Series Metadata",
      description:
        "WADO-RS metadata: one DICOM JSON object per instance in the " +
        "series, carrying the attributes the Cornerstone viewer needs.",
      params: {
        study: { description: WADORS_STUDY },
        series: { description: "A SeriesInstanceUID." },
      },
    }),
  );
}

/**
 * Split the "iec:123" / "timepoint:5" / "activity:7" study selector
 * used in place of a StudyInstanceUID.
 */
function parseWadorsStudy(study: string): [string, number] {
  const colon = study.indexOf(":");
  if (colon < 0) throw new HttpError(404, "Not Found");
  const kind = study.slice(0, colon);
  const raw = study.slice(colon + 1);
  if (!/^-?\d+$/.test(raw)) {
    throw new HttpError(422, "study selector id must be an integer");
  }
  if (kind !== "iec" && kind !== "timepoint" && kind !== "activity") {
    throw new HttpError(404, "Not Found");
  }
  return [kind, Number(raw)];
}

async function wadorsFrames(app: App, ctx: Ctx): Promise<Response> {
  const [kind, id] = parseWadorsStudy(pathStr(ctx, "study"));
  const sop = pathStr(ctx, "sop");

  let row: Row | undefined;
  if (kind === "iec") {
    row = await app.db.fetchOne(
      `
      select
          root_path || '/' || rel_path as file,
          pixel_data_offset as file_offset,
          xfer_syntax
      from
              image_equivalence_class_input_image
              natural join dicom_file
              natural join file_meta
              natural join file_sop_common
              natural join file_location
              natural join file_storage_root
      where
              image_equivalence_class_id = $1
              and sop_instance_uid = $2
      `,
      [id, sop],
    );
  } else if (kind === "timepoint") {
    row = await app.db.fetchOne(
      `
      select
          root_path || '/' || rel_path as file,
          pixel_data_offset as file_offset,
          xfer_syntax
      from
              activity_timepoint_file
              natural join dicom_file
              natural join file_meta
              natural join file_sop_common
              natural join file_location
              natural join file_storage_root
      where
              activity_timepoint_id = $1
              and sop_instance_uid = $2
      `,
      [id, sop],
    );
  } else {
    // The Python handler shares code with the timepoint variant and
    // queries with timepoint_id=None, which matches nothing.
    row = undefined;
  }
  if (!row) throw errNoRecords();

  const data = await readFileFrom(
    String(row.file ?? ""),
    Number(row.file_offset ?? 0),
  );
  return new Response(data as unknown as BodyInit, {
    headers: {
      "Content-Type": `application/octet-stream; transfer-syntax=${String(row.xfer_syntax ?? "")}`,
    },
  });
}

async function wadorsMetadata(app: App, ctx: Ctx): Promise<Response> {
  const [kind, id] = parseWadorsStudy(pathStr(ctx, "study"));
  const series = pathStr(ctx, "series");

  let rows: Row[];
  if (kind === "activity") {
    // Python raises HTTPException("not implemented yet") which crashes
    // response rendering -> 500.
    throw new InternalError();
  } else if (kind === "timepoint") {
    rows = await app.db.fetch(
      `
      select distinct
          root_path || '/' || rel_path as file,
          pixel_data_offset as file_offset,
          pixel_data_length as size,
          bits_stored,
          bits_allocated,
          high_bit,
          pixel_representation,
          pixel_columns,
          pixel_rows,
          photometric_interpretation,

          slope,
          intercept,

          window_width,
          window_center,
          pixel_pad,
          samples_per_pixel,
          planar_configuration,
          coalesce(number_of_frames, 1) as number_of_frames,
          iop,
          ipp,
          study_instance_uid,
          series_instance_uid,
          sop_instance_uid,
          pixel_spacing,
          file_id

      from
          activity_timepoint_file
          natural join file_series
          natural join file_study
          natural join file_sop_common
          natural join file_image
          natural join image
          natural join image_geometry
          natural join dicom_file
          natural join file_location
          natural join file_storage_root
          natural join file_equipment

          natural left join file_slope_intercept
          natural left join slope_intercept

          natural left join file_win_lev
          natural left join window_level

      where
          activity_timepoint_id = $1
          and series_instance_uid = $2
      order by file_id desc
      `,
      [id, series],
    );
  } else {
    rows = await app.db.fetch(
      `
      select distinct
          root_path || '/' || rel_path as file,
          pixel_data_offset as file_offset,
          pixel_data_length as size,
          bits_stored,
          bits_allocated,
          high_bit,
          pixel_representation,
          pixel_columns,
          pixel_rows,
          photometric_interpretation,

          slope,
          intercept,

          window_width,
          window_center,
          pixel_pad,
          samples_per_pixel,
          planar_configuration,
          coalesce(number_of_frames, 1) as number_of_frames,
          iop,
          ipp,
          study_instance_uid,
          series_instance_uid,
          sop_instance_uid,
          pixel_spacing,
          file_id,
          modality

      from
            image_equivalence_class_input_image
          natural join file_series
          natural join file_study
          natural join file_sop_common
          natural join file_image
          natural join image
          natural join dicom_file
          natural join file_location
          natural join file_storage_root
          natural join file_equipment

          natural left join image_geometry

          natural left join file_slope_intercept
          natural left join slope_intercept

          natural left join file_win_lev
          natural left join window_level

      where
            image_equivalence_class_id = $1
      order by file_id desc
      `,
      [id],
    );
  }

  return jsonResponse(rows.map(wadorsConvert));
}

/** Mirrors ValueModel.from_record. */
function newWadorsValue(vr: string, v: unknown): WadorsValue {
  let values: unknown[];
  if (v === null || v === undefined) {
    values = [];
  } else if (typeof v === "string") {
    values = v.includes("\\") ? v.split("\\") : [v];
  } else {
    values = [v];
  }

  if (vr === "US") {
    values = values.map(toInt);
  } else if (vr === "DS") {
    values = values.map(toFloat);
  }
  return { Value: values, vr };
}

function toInt(v: unknown): unknown {
  if (typeof v === "string" && /^-?\d+$/.test(v.trim())) {
    return Number(v.trim());
  }
  return v;
}

function toFloat(v: unknown): unknown {
  if (typeof v === "string") {
    const t = v.trim();
    const f = Number(t);
    if (t !== "" && !Number.isNaN(f)) return f;
    return v;
  }
  return v;
}

function wadorsConvert(row: Row): Record<string, WadorsValue> {
  const c = newWadorsValue;
  const ret: Record<string, WadorsValue> = {
    "00280030": c("DS", row.pixel_spacing),
    "00080018": c("UI", row.sop_instance_uid),
    "0020000E": c("UI", row.series_instance_uid),
    "0020000D": c("UI", row.study_instance_uid),
    "00280010": c("US", row.pixel_rows),
    "00280011": c("US", row.pixel_columns),
    "00280101": c("US", row.bits_stored),
    "00280100": c("US", row.bits_allocated),
    "00280102": c("US", row.high_bit),
    "00280103": c("US", row.pixel_representation),
    "00281053": c("DS", row.slope),
    "00281052": c("DS", row.intercept),
    "00281050": c("DS", row.window_center),
    "00281051": c("DS", row.window_width),
    "00280002": c("US", row.samples_per_pixel),
    "00280004": c("CS", row.photometric_interpretation),
    "00080060": c("CS", row.modality),
  };
  if (row.iop != null) ret["00200037"] = c("DS", row.iop);
  if (row.ipp != null) ret["00200032"] = c("DS", row.ipp);

  // The Go port serialized these maps with sorted keys; keep that
  // order for byte-comparable output.
  const sorted: Record<string, WadorsValue> = {};
  for (const key of Object.keys(ret).sort()) sorted[key] = ret[key]!;
  return sorted;
}
