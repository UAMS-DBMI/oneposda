// Ports papi/routes/iecs.py.

import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathInt, queryBool } from "../server";
import { HttpError, errNoRecords, jsonResponse } from "../httpx";
import type { Row } from "../db";
import { consistent, newImageFile, type ImageFile } from "../dicom";
import { fetchJson, firstColumn } from "./common";

/** GET /v1/iecs/{iec} — image_equivalence_class rows. */
export interface IEC {
  image_equivalence_class_id: number;
  series_instance_uid: string;
  equivalence_class_number: number | null;
  processing_status: string | null;
  review_status: string | null;
  update_user: string | null;
  update_date: string | null;
  hidden: boolean;
  visual_review_instance_id: number | null;
}

/** GET /v1/iecs/{iec}/info */
export interface IECInfo {
  visual_review_instance_id: number | null;
  image_equivalence_class_id: number;
  series_instance_uid: string;
  equivalence_class_number: number | null;
  processing_status: string | null;
  review_status: string | null;
  update_user: string | null;
  update_date: string | null;
  file_count: number;
  body_part_examined: string | null;
  modality: string | null;
  patient_id: string | null;
  series_description: string | null;
  frame_of_reference_uid: string | null;
  download_path: string;
  download_name: string;
  volumetric: boolean;
}

/** GET /v1/iecs/{iec}/other_iecs_in_for */
export interface IECSharingFOR {
  image_equivalence_class_id: number;
  series_instance_uid: string | null;
  series_description: string | null;
  modality: string | null;
  file_count: number;
}

export function registerIECs(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "listing all iecs is not allowed");
  };
  app.prot("GET", "/v1/iecs", notAllowed,
    doc({
      summary: "Get All Iecs",
      params: {
        request: { in: "query", required: true },
        kwargs: { in: "query", required: true },
      },
    }),
  );
  app.prot("GET", "/v1/iecs/", notAllowed,
    doc({
      summary: "Get All Iecs",
      params: {
        request: { in: "query", required: true },
        kwargs: { in: "query", required: true },
      },
    }),
  );

  app.prot("GET", "/v1/iecs/:iec", (ctx) =>
    // Python returns db.fetch here, so the response is a list.
    fetchJson(
      app,
      `
      select
          image_equivalence_class_id,
          series_instance_uid,
          equivalence_class_number,
          processing_status,
          review_status,
          update_user,
          update_date::text,
          hidden,
          visual_review_instance_id
      from image_equivalence_class
      where image_equivalence_class_id = $1
      `,
      [pathInt(ctx, "iec")],
      { update_date: "ts" },
    ),
    doc<IEC[]>({
      summary: "Get Iec Details",
      params: {
        iec: { type: "integer" },
      },
    }),
  );

  app.prot("GET", "/v1/iecs/:iec/files", (ctx) => getIECFiles(app, ctx),
    doc({
      summary: "Get Iec Files",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/iecs/:iec/frames", (ctx) => getIECFrames(app, ctx),
    doc({
      summary: "Get Iec Frames",
      description: "Get a list of frames (files and frame counts) from this IEC.\n\nAlso returns a guess for if the data is intended to be volumetric.",
      params: {
        iec: { type: "integer" },
        include_frames: { in: "query", type: "boolean" },
      },
    }),
  );
  app.prot("GET", "/v1/iecs/:iec/info", (ctx) => getIECInfo(app, ctx),
    doc<IECInfo>({
      summary: "Get Iec Info",
      description: "Get details for an IEC.",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/iecs/:iec/other_iecs_in_for", (ctx) =>
    fetchJson(
      app,
      `
      with input_for as (
          select distinct for_uid, visual_review_instance_id
          from image_equivalence_class_input_image
          natural join image_equivalence_class
          natural join file_for
          where image_equivalence_class_id = $1
          limit 1
      ), candidate_files as (
          select file_id, image_equivalence_class_id
          from image_equivalence_class
          natural join image_equivalence_class_input_image
          where visual_review_instance_id = (select visual_review_instance_id from input_for)
      )
      select image_equivalence_class_id,
             series_instance_uid,
             series_description,
             modality,
             count(file_id) as file_count
      from candidate_files
      natural join file_for
      natural join file_series
      where for_uid = (select for_uid from input_for)
      and image_equivalence_class_id != $1
      group by 1, 2, 3, 4
      order by file_count desc
      `,
      [pathInt(ctx, "iec")],
      { file_count: "int8" },
    ),
    doc<IECSharingFOR[]>({
      summary: "Iecs For For",
      description: "Get all other IECs that share this IEC's Frame of Reference\n\nFor the given IEC, this returns a list of all IECs (other than\nthe original one) inside the same visual review that share a\nFrame of Reference.",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
}

async function getIECFiles(app: App, ctx: Ctx): Promise<Response> {
  const rows = await app.db.fetch(
    `
    select
        file_id
    from
        image_equivalence_class_input_image
        natural join file_sop_common
    where
        image_equivalence_class_id = $1
    order by
        -- sometimes instance_number is empty string or null
        case instance_number
            when '' then '0'
            when null then '0'
            else instance_number
        end::int
    `,
    [pathInt(ctx, "iec")],
  );
  return jsonResponse({ file_ids: firstColumn(rows) });
}

const iecFramesQuery = `
    select distinct
        file_id,
        file_storage_root_id || '/' || rel_path as path,
        image_type,
        coalesce(number_of_frames, 1) as frame_count,
        iop,
        ipp
    from
        image_equivalence_class_input_image
        natural join file_location
        natural left join file_image
        natural left join image
        natural left join image_geometry
    where
        image_equivalence_class_id = $1
`;

/**
 * Build ImageFiles from a frame-listing query and apply the volumetric
 * consistency check, returning the sorted files.
 */
export function iecFrameList(rows: Row[]): [ImageFile[], boolean] {
  const files = rows.map((row) =>
    newImageFile(
      row.file_id as number,
      String(row.path ?? ""),
      typeof row.image_type === "string" ? row.image_type : "",
      Number(row.frame_count ?? 0),
      typeof row.iop === "string" ? row.iop : "",
      typeof row.ipp === "string" ? row.ipp : "",
    ),
  );
  return consistent(files);
}

function frameListJson(files: ImageFile[]): unknown[] {
  return files.map((f) => ({
    file_id: f.fileId,
    path: f.path,
    num_of_frames: f.frameCount,
  }));
}

async function getIECFrames(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");
  const includeFrames = queryBool(ctx, "include_frames", true);

  const rows = await app.db.fetch(iecFramesQuery, [iec]);
  if (rows.length === 0) throw errNoRecords();

  const [sorted, volumetric] = iecFrameList(rows);

  if (!includeFrames) {
    return jsonResponse({ volumetric });
  }
  return jsonResponse({ volumetric, frames: frameListJson(sorted) });
}

async function getIECInfo(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");

  // Volumetric guess, same as the /frames endpoint (404 when the IEC
  // has no files at all).
  const frameRows = await app.db.fetch(iecFramesQuery, [iec]);
  if (frameRows.length === 0) throw errNoRecords();
  const [, volumetric] = iecFrameList(frameRows);

  const row = await app.db.fetchOne(
    `
    select
        visual_review_instance_id,
        image_equivalence_class_id,
        series_instance_uid,
        equivalence_class_number,
        processing_status,
        review_status,
        update_user,
        to_char(update_date, 'YYYY-MM-DD HH:MI:SS AM') as update_date,
        (select count(file_id)
         from image_equivalence_class_input_image i
         where i.image_equivalence_class_id =
               image_equivalence_class.image_equivalence_class_id) as file_count,
        (select body_part_examined
         from file_series
         where file_series.series_instance_uid = image_equivalence_class.series_instance_uid limit 1) as body_part_examined,
        (select modality
         from file_series
         where file_series.series_instance_uid = image_equivalence_class.series_instance_uid limit 1) as modality,
        (select patient_id
         from file_patient
         natural join file_series
         where file_series.series_instance_uid = image_equivalence_class.series_instance_uid limit 1) as patient_id,
        (select series_description
         from image_equivalence_class_input_image
         natural join file_series
         where image_equivalence_class_input_image.image_equivalence_class_id = image_equivalence_class.image_equivalence_class_id
         limit 1
        ) as series_description,
        (select for_uid
         from image_equivalence_class_input_image
         natural join file_for
         where image_equivalence_class_input_image.image_equivalence_class_id = image_equivalence_class.image_equivalence_class_id
         limit 1
        ) as frame_of_reference_uid
    from image_equivalence_class
    where image_equivalence_class_id = $1
    `,
    [iec],
    { file_count: "int8" },
  );
  if (!row) {
    // dict([]) in Python produces an empty object response.
    return jsonResponse({});
  }

  row.download_path = `/papi/v1/files/iec/${iec}`;
  row.download_name = `iec_${iec}.zip`;
  row.volumetric = volumetric;
  return jsonResponse(row);
}
