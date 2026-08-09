// Ports papi/routes/files.py.

import { readdirSync, statSync } from "node:fs";
import type { App, Ctx } from "../server";
import { doc, type OrEmpty } from "../openapi";
import { pathInt, pathStr, queryStr } from "../server";
import { HttpError, errNoRecords, jsonResponse } from "../httpx";
import { fetchOneJson, firstColumn, readFileFrom, serveFile } from "./common";
import { streamZip } from "../archive";
import { parseSeriesSpec } from "./series";

/** GET /v1/files/{file_id} — file rows. */
export interface FileRow {
  file_id: number;
  digest: string;
  size: number | null;
  is_dicom_file: boolean | null;
  file_type: string | null;
  processing_priority: number | null;
  ready_to_process: boolean | null;
}

/** GET /v1/files/{file_id}/path */
export interface FilePath {
  file_path: string | null;
}

/** GET /v1/files/{file_id}/details */
export interface FileDetails {
  file: string | null;
  file_offset: number | null;
  size: number | null;
  bits_stored: number | null;
  bits_allocated: number | null;
  pixel_representation: number | null;
  pixel_columns: number | null;
  pixel_rows: number | null;
  photometric_interpretation: string | null;
  slope: string | null;
  intercept: string | null;
  window_width: string | null;
  window_center: string | null;
  pixel_pad: number | null;
  project_name: string | null;
  site_name: string | null;
  sop_instance_uid: string | null;
  series_instance_uid: string | null;
  modality: string | null;
  body_part_examined: string | null;
  series_description: string | null;
  patient_id: string | null;
  study_instance_uid: string | null;
}

export function registerFiles(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "listing all files is not allowed");
  };
  app.prot("GET", "/v1/files", notAllowed,
    doc({
      summary: "Get All Files",
    }),
  );
  app.prot("GET", "/v1/files/", notAllowed,
    doc({
      summary: "Get All Files",
    }),
  );

  app.prot("GET", "/v1/files/listfiles", (ctx) => getListFiles(ctx),
    doc({
      summary: "Get Listfiles",
      params: {
        path: { in: "query", required: true },
      },
    }),
  );
  app.prot("GET", "/v1/files/:file_id", (ctx) =>
    fetchOneJson(
      app,
      `
      select
          file_id,
          digest,
          size,
          is_dicom_file,
          file_type,
          processing_priority,
          ready_to_process
      from file
      where file_id = $1
      `,
      [pathInt(ctx, "file_id")],
    ),
    doc<OrEmpty<FileRow>>({
      summary: "Get Single File",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/files/series/:spec", (ctx) => getSeriesZip(app, ctx),
    doc({
      summary: "Get Series Files",
      description:
        "Every file in the series, as a STORED (uncompressed) zip archive " +
        "streamed as it is built.",
      params: {
        spec: {
          description:
            "A SeriesInstanceUID, optionally suffixed with `@<activity_id>` " +
            "or `:<activity_timepoint_id>` to select the files as they were " +
            "in that activity or timepoint rather than the current ones.",
        },
      },
      produces: "application/zip",
    }),
  );
  app.prot("GET", "/v1/files/iec/:iec", (ctx) => getIECZip(app, ctx),
    doc({
      summary: "Get Iec Files",
      params: {
        iec: { type: "integer" },
      },
    }),
  );

  app.prot("GET", "/v1/files/:file_id/pixels", (ctx) => getPixelData(app, ctx),
    doc({
      summary: "Get Pixel Data",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/files/:file_id/data", (ctx) => getFileData(app, ctx),
    doc({
      summary: "Get Data",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/files/:file_id/data.gz", (ctx) => getFileData(app, ctx),
    doc({
      summary: "Get Data",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/files/:file_id/path", (ctx) =>
    fetchOneJson(
      app,
      `
      select
          root_path || '/' || rel_path as file_path
      from file
      natural join file_location
      natural join file_storage_root
      where file_id = $1
      `,
      [pathInt(ctx, "file_id")],
    ),
    doc<OrEmpty<FilePath>>({
      summary: "Get Path",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/files/:file_id/details", (ctx) =>
    getFileDetails(app, ctx),
    doc<OrEmpty<FileDetails>>({
      summary: "Get Details",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
}

function getListFiles(ctx: Ctx): Response {
  const root = queryStr(ctx, "path", "");
  const files: string[] = [];
  // Lexical-order recursive walk; unreadable entries are skipped
  // silently like os.walk.
  const walk = (dir: string): void => {
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    entries.sort((a, b) => (a.name < b.name ? -1 : 1));
    for (const entry of entries) {
      const full = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        walk(full);
      } else {
        files.push(full);
        if (files.length > 5000) {
          throw new HttpError(400, "More than 5000 results. I refuse.");
        }
      }
    }
  };
  walk(root);
  return jsonResponse(files);
}

async function getSeriesZip(app: App, ctx: Ctx): Promise<Response> {
  const spec = parseSeriesSpec(pathStr(ctx, "spec"));

  let sql: string;
  let args: unknown[];
  let fileName: string;
  if (spec.timepointId !== null) {
    sql = `
    select distinct root_path || '/' || rel_path as file
    from file_series
    natural left join ctp_file
    natural left join file_location
    natural left join file_storage_root
    natural left join activity_timepoint_file
    where series_instance_uid = $1
      and activity_timepoint_id = $2
    `;
    args = [spec.uid, spec.timepointId];
    fileName = `${spec.uid}_tp${spec.timepointId}.zip`;
  } else if (spec.activityId !== null) {
    sql = `
    select distinct root_path || '/' || rel_path as file
    from file_series
    natural left join ctp_file
    natural left join file_location
    natural left join file_storage_root
    natural left join activity_timepoint_file
    where series_instance_uid = $1
    and activity_timepoint_id = (
        select max(activity_timepoint_id)
        from activity_timepoint
        where activity_id = $2
    )
    `;
    args = [spec.uid, spec.activityId];
    fileName = `${spec.uid}_act${spec.activityId}.zip`;
  } else {
    sql = `
    select distinct root_path || '/' || rel_path as file
    from file_series
    natural left join ctp_file
    natural left join file_location
    natural left join file_storage_root
    where series_instance_uid = $1
    `;
    args = [spec.uid];
    fileName = `${spec.uid}_ALL.zip`;
  }

  const rows = await app.db.fetch<{ file: string | null }>(sql, args);
  return streamZip(
    rows.map((row) => row.file ?? ""),
    fileName,
  );
}

async function getIECZip(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");
  const rows = await app.db.fetch<{ file: string | null }>(
    `
    select root_path || '/' || rel_path as file
    from
    image_equivalence_class_input_image
    natural left join ctp_file
    natural left join file_location
    natural left join file_storage_root
    where image_equivalence_class_id = $1
    `,
    [iec],
  );
  return streamZip(
    rows.map((row) => row.file ?? ""),
    `${iec}.zip`,
  );
}

/**
 * Render a value the way Python's str() does inside the Q-DICOM
 * response headers (None for nulls, True/False for bools).
 */
function pyStr(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (typeof v === "boolean") return v ? "True" : "False";
  return String(v);
}

async function getPixelData(app: App, ctx: Ctx): Promise<Response> {
  const fileId = pathInt(ctx, "file_id");

  const row = await app.db.fetchOne(
    `
    select distinct
        root_path || '/' || rel_path as file,
        pixel_data_offset as file_offset,
        pixel_data_length as size,
        bits_stored,
        bits_allocated,
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
        coalesce(number_of_frames, 1) as number_of_frames

    from
        file_image
        natural join image
        natural join dicom_file
        natural join file_location
        natural join file_storage_root
        natural join file_equipment

        natural left join file_slope_intercept
        natural left join slope_intercept

        natural left join file_win_lev
        natural left join window_level

    where file_image.file_id = $1
    `,
    [fileId],
  );
  if (!row) throw errNoRecords();

  const data = await readFileFrom(
    String(row.file ?? ""),
    Number(row.file_offset ?? 0),
  );

  return new Response(data as unknown as BodyInit, {
    headers: {
      "Q-DICOM-Rows": pyStr(row.pixel_rows),
      "Q-DICOM-Cols": pyStr(row.pixel_columns),
      "Q-DICOM-Size": pyStr(row.size),
      "Q-DICOM-Bits-Stored": pyStr(row.bits_stored),
      "Q-DICOM-Bits-Allocated": pyStr(row.bits_allocated),
      "Q-DICOM-PixelRep": pyStr(row.pixel_representation),
      "Q-DICOM-Slope": pyStr(row.slope),
      "Q-DICOM-Intercept": pyStr(row.intercept),
      "Q-DICOM-Window-Center": pyStr(row.window_center),
      "Q-DICOM-Window-Width": pyStr(row.window_width),
      "Q-DICOM-Pixel-Pad": pyStr(row.pixel_pad),
      "Q-DICOM-Samples-Per-Pixel": pyStr(row.samples_per_pixel),
      "Q-DICOM-PhotoRep": pyStr(row.photometric_interpretation),
      "Q-DICOM-Planar-Config": pyStr(row.planar_configuration),
      "Q-DICOM-Num-of-Frames": pyStr(row.number_of_frames),
      "Content-Type": "application/octet-stream",
    },
  });
}

/** Resolve a file_id to its path via file_location. */
export async function fileOnDisk(app: App, fileId: number): Promise<string> {
  const row = await app.db.fetchOne<{ file: string | null }>(
    `
    select
        root_path || '/' || rel_path as file,
        size
    from file
    natural join file_location
    natural join file_storage_root
    where file_id = $1
    `,
    [fileId],
  );
  if (!row) throw errNoRecords();
  const path = row.file ?? "";
  try {
    statSync(path);
  } catch {
    throw new HttpError(404, "File not found on disk");
  }
  return path;
}

async function getFileData(app: App, ctx: Ctx): Promise<Response> {
  const path = await fileOnDisk(app, pathInt(ctx, "file_id"));
  return serveFile(ctx.req, path);
}

async function getFileDetails(app: App, ctx: Ctx): Promise<Response> {
  return fetchOneJson(
    app,
    `
    select distinct
        root_path || '/' || rel_path as file,
        file_offset,
        size,
        bits_stored,
        bits_allocated,
        pixel_representation,
        pixel_columns,
        pixel_rows,
        photometric_interpretation,

        slope,
        intercept,

        window_width,
        window_center,
        pixel_pad,

        project_name,
        site_name,
        sop_instance_uid,
        series_instance_uid,
        modality,
        body_part_examined,
        series_description,
        patient_id,
        study_instance_uid

    from
        file
        natural left join file_image
        natural left join image
        natural left join unique_pixel_data
        natural left join pixel_location
        natural left join file_location
        natural left join file_storage_root
        natural left join file_equipment
        natural left join file_sop_common
        natural left join file_series
        natural left join ctp_file
        natural left join file_patient
        natural left join file_study

        natural left join file_slope_intercept
        natural left join slope_intercept

        natural left join file_win_lev
        natural left join window_level

    where file.file_id = $1
    `,
    [pathInt(ctx, "file_id")],
  );
}
