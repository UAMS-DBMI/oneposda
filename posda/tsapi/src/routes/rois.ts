// Ports papi/routes/rois.py.

import { open } from "node:fs/promises";
import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathInt, pathStr } from "../server";
import { HttpError, errNoRecords, jsonResponse } from "../httpx";
import {
  formatColor,
  makeTransform,
  parseBackslashFloats,
  parseContourPoints,
  transformContour,
} from "../dicom";

/** GET /v1/rois/series/{series_instance_uid} elements. */
export interface SeriesRoi {
  roi_num: number | null;
  name: string | null;
  color: [number, number, number];
  file_ids: number[];
}

/** GET /v1/rois/sop/{sop_instance_uid} elements. */
export interface SopContour {
  name: string | null;
  color: [number, number, number];
  points: [number, number][];
}

interface ContourRow {
  roi_num: number | null;
  roi_name: string | null;
  roi_color: string | null;
  image_file_id: number;
  file_id: number;
  data_set_start: number | null;
  contour_file_offset: number | null;
  contour_length: number | null;
  num_points: number | null;
  true_offset: number | null;
  filename: string | null;
  iop: string | null;
  ipp: string | null;
  pixel_spacing: string | null;
}

export function registerROIs(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "test error, not allowed");
  };
  app.prot("GET", "/v1/rois", notAllowed,
    doc({
      summary: "Test",
    }),
  );
  app.prot("GET", "/v1/rois/", notAllowed,
    doc({
      summary: "Test",
    }),
  );

  app.prot("GET", "/v1/rois/series/:series_instance_uid", (ctx) =>
    roisForSeries(app, pathStr(ctx, "series_instance_uid")),
    doc<SeriesRoi[]>({
      summary: "Get Rois For Series",
    }),
  );
  app.prot("GET", "/v1/rois/file/:file_id/series", (ctx) =>
    getSeriesROIsFromFile(app, ctx),
    doc<SeriesRoi[]>({
      summary: "Get Series Rois From File",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/rois/sop/:sop_instance_uid", (ctx) =>
    contoursForSOP(app, pathStr(ctx, "sop_instance_uid")),
    doc<SopContour[]>({
      summary: "Get Contours For Sop",
    }),
  );
  app.prot("GET", "/v1/rois/file/:file_id", (ctx) =>
    getContoursForFile(app, ctx),
    doc({
      summary: "Get Contours For File",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
}

async function roisForSeries(app: App, uid: string): Promise<Response> {
  const rows = await app.db.fetch(
    `
    select
        roi_num,
        roi_name as name,
        roi_color as color,
        array_agg(file_sop_common.file_id) as file_ids
    from file_series
    natural join file_sop_common
    join file_roi_image_linkage
        on linked_sop_instance_uid = sop_instance_uid
    natural join roi
    where series_instance_uid = $1
    group by roi_num, roi_name, roi_color
    order by roi_num
    `,
    [uid],
  );

  const out: SeriesRoi[] = rows.map((row) => ({
    roi_num: row.roi_num as number | null,
    name: row.name as string | null,
    color: formatColor(typeof row.color === "string" ? row.color : null),
    file_ids: row.file_ids as number[],
  }));
  return jsonResponse(out);
}

async function getSeriesROIsFromFile(app: App, ctx: Ctx): Promise<Response> {
  const row = await app.db.fetchOne<{ series_instance_uid: string | null }>(
    `
    select series_instance_uid
    from file_series
    where file_id = $1
    `,
    [pathInt(ctx, "file_id")],
  );
  if (!row) throw errNoRecords();
  return roisForSeries(app, row.series_instance_uid ?? "");
}

async function contoursForSOP(app: App, sop: string): Promise<Response> {
  const rows = await app.db.fetch<ContourRow>(
    `
    select
            roi_num,
            roi_name,
            roi_color,
            file_sop_common.file_id as image_file_id,
            fril.file_id as file_id,
            data_set_start,
            contour_file_offset,
            contour_length,
            num_points,
            data_set_start + contour_file_offset as true_offset,
            (
                select root_path || '/' || rel_path
                from file_location
                natural join file_storage_root
                where file_location.file_id = fril.file_id
                limit 1
            ) as filename,
            (
                select iop
                from file_image
                natural join image_geometry
                where file_image.file_id = file_sop_common.file_id
                limit 1
            ) as iop,
            (
                select ipp
                from file_image
                natural join image_geometry
                where file_image.file_id = file_sop_common.file_id
                limit 1
            ) as ipp,
            (
                select pixel_spacing
                from file_image
                natural join image
                where file_image.file_id = file_sop_common.file_id
                limit 1
            ) as pixel_spacing
    from file_sop_common
    join file_roi_image_linkage fril
            on fril.linked_sop_instance_uid = file_sop_common.sop_instance_uid
    join ctp_file
            on fril.file_id = ctp_file.file_id
    join file_meta
            on file_meta.file_id = fril.file_id
    natural join roi
    where sop_instance_uid = $1
    `,
    [sop],
  );

  const contours: SopContour[] = [];
  for (const row of rows) {
    contours.push({
      name: row.roi_name,
      color: formatColor(row.roi_color),
      points: await transformedContour(row),
    });
  }
  return jsonResponse(contours);
}

/**
 * Ports roi.get_transformed_contour: read the raw contour bytes out of
 * the RTSTRUCT file and project them into pixel coordinates for the
 * linked image.
 */
async function transformedContour(row: ContourRow): Promise<[number, number][]> {
  const length = row.contour_length ?? 0;
  const data = new Uint8Array(length);
  const fh = await open(row.filename ?? "", "r");
  try {
    await fh.read(data, 0, length, row.true_offset ?? 0);
  } finally {
    await fh.close();
  }

  const points = parseContourPoints(new TextDecoder().decode(data));
  if (points.length !== (row.num_points ?? 0)) {
    console.warn("Warning: actual point count != calculated count!");
  }

  const xform = makeTransform(
    parseBackslashFloats(row.iop ?? ""),
    parseBackslashFloats(row.ipp ?? ""),
  );
  return transformContour(points, xform, parseBackslashFloats(row.pixel_spacing ?? ""));
}

async function getContoursForFile(app: App, ctx: Ctx): Promise<Response> {
  const row = await app.db.fetchOne<{ sop_instance_uid: string | null }>(
    `
    select sop_instance_uid
    from file_sop_common
    where file_id = $1
    `,
    [pathInt(ctx, "file_id")],
  );
  if (!row) throw errNoRecords();
  return contoursForSOP(app, row.sop_instance_uid ?? "");
}
