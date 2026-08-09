// Ports papi/routes/visualreviews.py.

import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathInt } from "../server";
import { HttpError, jsonResponse } from "../httpx";
import { decodeJsonBody, fetchJson, fetchFirstColumn, firstColumn } from "./common";

/** GET /v1/visualreviews/{vr} — visual_review_instance rows. */
export interface VisualReviewInstance {
  visual_review_instance_id: number;
  subprocess_invocation_id: number | null;
  visual_review_reason: string | null;
  visual_review_scheduler: string | null;
  visual_review_num_series: number | null;
  when_visual_review_scheduled: string | null;
  visual_review_num_series_done: number | null;
  visual_review_num_equiv_class: number | null;
  when_visual_review_sched_complete: string | null;
}

/** GET /v1/visualreviews/{vr}/values */
export interface VisualReviewValues {
  dicom_file_types: { dicom_file_type: string | null; count: number }[];
  review_statuses: { review_status: string | null; count: number }[];
  processing_statuses: { processing_status: string | null; count: number }[];
}

/**
 * A filter parameter shared by the visualreviews and masking filter
 * endpoints: absent or "*" means no filtering, null means "is null".
 */
export type FilterValue = string | null;

export function appendFilter(
  body: Record<string, unknown>,
  key: string,
  column: string,
  query: { sql: string },
  args: unknown[],
): void {
  if (!(key in body)) return; // defaults to "*", meaning no filter
  const raw = body[key];
  const value: FilterValue =
    raw === null ? null : typeof raw === "string" ? raw : JSON.stringify(raw);
  if (value === "*") return;
  if (value === null) {
    query.sql += `and ${column} is null\n`;
    return;
  }
  args.push(value);
  query.sql += `and ${column} = $${args.length}\n`;
}

export function registerVisualReviews(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "listing all VRs is not allowed");
  };
  app.prot("GET", "/v1/visualreviews", notAllowed,
    doc({
      summary: "Get All Iecs",
      params: {
        request: { in: "query", required: true },
        kwargs: { in: "query", required: true },
      },
    }),
  );
  app.prot("GET", "/v1/visualreviews/", notAllowed,
    doc({
      summary: "Get All Iecs",
      params: {
        request: { in: "query", required: true },
        kwargs: { in: "query", required: true },
      },
    }),
  );

  app.prot("GET", "/v1/visualreviews/:vr", (ctx) =>
    fetchJson(
      app,
      `
      select
          visual_review_instance_id,
          subprocess_invocation_id,
          visual_review_reason,
          visual_review_scheduler,
          visual_review_num_series,
          when_visual_review_scheduled::text,
          visual_review_num_series_done,
          visual_review_num_equiv_class,
          when_visual_review_sched_complete::text
      from visual_review_instance
      where visual_review_instance_id = $1
      `,
      [pathInt(ctx, "vr")],
      {
        when_visual_review_scheduled: "ts",
        when_visual_review_sched_complete: "ts",
      },
    ),
    doc<VisualReviewInstance[]>({
      summary: "Get Vr Details",
      description: "Get details about a specific Visual Review (VR)",
      params: {
        vr: { type: "integer" },
      },
    }),
  );

  app.prot("GET", "/v1/visualreviews/:vr/iecs", (ctx) =>
    fetchFirstColumn(
      app,
      `
      select
          image_equivalence_class_id
      from
          image_equivalence_class
      where
          visual_review_instance_id = $1
      order by 1
      `,
      [pathInt(ctx, "vr")],
    ),
    doc({
      summary: "Get Vr Iecs",
      description: "Get the list of IECs contained in this VR\n\nResults are always in ascending order.",
      params: {
        vr: { type: "integer" },
      },
    }),
  );

  app.prot("GET", "/v1/visualreviews/:vr/values", (ctx) =>
    getVRValues(app, ctx),
    doc<VisualReviewValues>({
      summary: "Get Vr Extra Details",
      description: "Get list of valid values for use in filtering, for the given VR.\n\nReturns the valid values for: review_status, processing_status, and \ndicom_file_type",
      params: {
        vr: { type: "integer" },
      },
    }),
  );
  app.prot("POST", "/v1/visualreviews/:vr/filter", (ctx) =>
    getVRFiltered(app, ctx),
    doc({
      summary: "Get Vr Filtered",
      description: "Return a filtered list of IECs in this VR. Use * for wildcard.\n\nResults are always in ascending order.",
      params: {
        vr: { type: "integer" },
      },
      requestBody: {
        contentType: "application/json",
        fields: {
          dicom_file_type: {  },
          processing_status: {  },
          review_status: {  },
        },
      },
    }),
  );
}

/**
 * Double-check a visual_review_instance_id; used when queries come
 * back empty to distinguish "no data" from "bad id".
 */
export async function vrExists(app: App, vr: number): Promise<boolean> {
  const rows = await app.db.fetch(
    `
    select visual_review_instance_id
    from visual_review_instance
    where visual_review_instance_id = $1
    `,
    [vr],
  );
  return rows.length > 0;
}

async function getVRValues(app: App, ctx: Ctx): Promise<Response> {
  const vr = pathInt(ctx, "vr");

  const dicomFileTypes = await app.db.fetch(
    `
    with iecs as (
        select image_equivalence_class_id, review_status, processing_status
        from image_equivalence_class
        where visual_review_instance_id = $1
    )
    select
        (
            select dicom_file_type
            from image_equivalence_class_input_image
            natural join dicom_file
            where image_equivalence_class_input_image.image_equivalence_class_id = iecs.image_equivalence_class_id
            limit 1
        ),
        count(*)
    from iecs
    group by 1
    `,
    [vr],
    { count: "int8" },
  );

  const reviewStatuses = await app.db.fetch(
    `
    select
        review_status,
        count(*) as count
    from image_equivalence_class
    where visual_review_instance_id = $1
    group by 1
    `,
    [vr],
    { count: "int8" },
  );

  const processingStatuses = await app.db.fetch(
    `
    select
        processing_status,
        count(*) as count
    from image_equivalence_class
    where visual_review_instance_id = $1
    group by 1
    `,
    [vr],
    { count: "int8" },
  );

  if (
    dicomFileTypes.length === 0 &&
    reviewStatuses.length === 0 &&
    processingStatuses.length === 0 &&
    !(await vrExists(app, vr))
  ) {
    throw new HttpError(404, "invalid visual review id");
  }

  return jsonResponse({
    dicom_file_types: dicomFileTypes,
    review_statuses: reviewStatuses,
    processing_statuses: processingStatuses,
  });
}

async function getVRFiltered(app: App, ctx: Ctx): Promise<Response> {
  const vr = pathInt(ctx, "vr");
  const body = await decodeJsonBody<Record<string, unknown>>(ctx.req);

  const query = {
    sql: `
    with iecs as (
        select
        image_equivalence_class_id,
        review_status,
        processing_status,
            (
                /*
                        All files in an IEC must always be of the same dicom_file_type,
                        so we can just select the first one here for speed
                */
                select dicom_file_type
                from image_equivalence_class_input_image
                natural join dicom_file
                where image_equivalence_class_input_image.image_equivalence_class_id =
                        image_equivalence_class.image_equivalence_class_id
                limit 1
            ) dicom_file_type
        from image_equivalence_class
        where visual_review_instance_id = $1
    )

    select image_equivalence_class_id
    from iecs
    where 1 = 1
    `,
  };
  const args: unknown[] = [vr];
  appendFilter(body, "dicom_file_type", "dicom_file_type", query, args);
  appendFilter(body, "processing_status", "processing_status", query, args);
  appendFilter(body, "review_status", "review_status", query, args);
  query.sql += "order by 1";

  const rows = await app.db.fetch(query.sql, args);

  if (rows.length === 0 && !(await vrExists(app, vr))) {
    throw new HttpError(404, "invalid visual review id");
  }

  return jsonResponse(firstColumn(rows));
}
