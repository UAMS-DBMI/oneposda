// Ports papi/routes/dicom_roots.py.

import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathInt } from "../server";
import { HttpError, InternalError, jsonResponse } from "../httpx";
import { isInvalidTextRepresentation, isUniqueViolation } from "../db";
import { decodeJsonBody, fetchJson } from "./common";

/** GET /v1/dicom_roots/searchRoots — submissions joined with codes. */
export interface SubmissionRoot {
  collection_name: string;
  collection_code: string;
  site_name: string;
  site_code: string;
  patient_id_prefix: string | null;
  body_part: string | null;
  access_type: string | null;
  baseline_date: string | null;
  date_shift: number | null;
  uid_root: string | null;
}

interface Submission {
  input_site_code?: number;
  input_site_name?: string;
  input_collection_code?: number;
  input_collection_name?: string;
  input_patient_id_prefix?: string;
  input_body_part?: string;
  input_access_type?: string;
  input_baseline_date?: string | null;
  input_date_shift?: string | null;
  input_uid_root?: string | null;
}

export function registerDicomRoots(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "test error");
  };
  app.prot("GET", "/v1/dicom_roots", notAllowed,
    doc({
      summary: "Get All Roots",
    }),
  );
  app.prot("GET", "/v1/dicom_roots/", notAllowed,
    doc({
      summary: "Get All Roots",
    }),
  );

  app.prot("GET", "/v1/dicom_roots/searchRoots", (ctx) => searchRoots(app, ctx),
    doc<SubmissionRoot[]>({
      summary: "Search Roots",
      description: "Search the roots (submissions) table using a variety of fields",
      params: {
        site_code: { in: "query" },
        collection_code: { in: "query" },
        site_name: { in: "query" },
        collection_name: { in: "query" },
        patient_id_prefix: { in: "query" },
        body_part: { in: "query" },
        access_type: { in: "query" },
        baseline_date: { in: "query" },
        date_shift: { in: "query" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/dicom_roots/findCollectionNameFromCode/:collection_code",
    (ctx) =>
      findName(app, ctx, "collection_code", `
        select
         collection_name
        from
         collection_codes
        where
         collection_code = $1
        `),
    doc({
      summary: "Find Collection Name From Code",
      params: {
        collection_code: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/dicom_roots/findSiteNameFromCode/:site_code", (ctx) =>
    findName(app, ctx, "site_code", `
       select
        site_name
       from
        site_codes
       where
        site_code = $1
       `),
    doc({
      summary: "Find Site Name From Code",
      params: {
        site_code: { type: "integer" },
      },
    }),
  );
  app.prot("POST", "/v1/dicom_roots/addNewSubmission", (ctx) =>
    addNewSubmission(app, ctx),
    doc({
      summary: "Add New Submission",
      requestBody: {
        contentType: "application/json",
        fields: {
          input_site_code: { type: "integer", required: true },
          input_site_name: { required: true },
          input_collection_code: { type: "integer", required: true },
          input_collection_name: { required: true },
          input_patient_id_prefix: { required: true },
          input_body_part: { required: true },
          input_access_type: { required: true },
          input_baseline_date: {  },
          input_date_shift: {  },
          input_uid_root: {  },
        },
      },
    }),
  );
}

async function searchRoots(app: App, ctx: Ctx): Promise<Response> {
  let where = "where 1 = 1 ";
  const values: unknown[] = [];

  const addLike = (param: string, clause: string): void => {
    if (ctx.url.searchParams.has(param)) {
      values.push(ctx.url.searchParams.get(param));
      where += `and ${clause} like $${values.length} `;
    }
  };

  addLike("site_code", "site_code");
  addLike("collection_code", "collection_code");
  addLike("site_name", "site_name");
  addLike("collection_name", "collection_name");
  addLike("patient_id_prefix", "patient_id_prefix");
  addLike("body_part", "body_part");

  if (ctx.url.searchParams.has("access_type")) {
    const at = ctx.url.searchParams.get("access_type")!;
    if (at !== "public" && at !== "limited") {
      throw new HttpError(422, "access_type must be one of: public, limited");
    }
    values.push(at);
    where += `and access_type = $${values.length} `;
  }

  addLike("baseline_date", "baseline_date::text");
  addLike("date_shift", "date_shift::text");

  return fetchJson(
    app,
    `
    select
    b.collection_name,
    b.collection_code,
    c.site_name,
    c.site_code,
    a.patient_id_prefix,
    a.body_part,
    a.access_type,
    a.baseline_date::text,
    a.date_shift,
    a.uid_root
    from
        submissions a
        natural join collection_codes b
        natural join site_codes c
        ${where}
    `,
    values,
    { baseline_date: "ts" },
  );
}

async function findName(
  app: App,
  ctx: Ctx,
  param: string,
  sql: string,
): Promise<Response> {
  const code = pathInt(ctx, param);
  const row = await app.db.fetchOne(sql, [String(code)]);
  if (!row) throw new InternalError();
  return new Response(String(Object.values(row)[0] ?? ""), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

async function addNewSubmission(app: App, ctx: Ctx): Promise<Response> {
  const sub = await decodeJsonBody<Submission>(ctx.req);
  for (const key of ["input_site_code", "input_collection_code"] as const) {
    if (key in sub && !Number.isInteger(sub[key])) {
      throw new HttpError(422, `invalid JSON body: ${key} must be an integer`);
    }
  }
  const siteCode = String(sub.input_site_code ?? 0);
  const collectionCode = String(sub.input_collection_code ?? 0);

  // The specific JSON message bodies below are expected verbatim by
  // the frontend.
  const site = await app.db.fetchOne(
    `
    select
     site_name
    from
     site_codes
    where
     site_code = $1
    `,
    [siteCode],
  );
  if (!site) {
    try {
      await app.db.exec(
        "insert into site_codes (site_code, site_name) values ($1, $2)",
        [siteCode, sub.input_site_name ?? ""],
      );
    } catch (err) {
      if (isUniqueViolation(err)) {
        return jsonResponse(
          {
            message:
              "Your site code or site name is already in use. Please choose a unique code and name \n",
          },
          422,
        );
      }
      return jsonResponse(
        { message: `An unexpected error occurred: \n${errMessage(err)}` },
        500,
      );
    }
  }

  const coll = await app.db.fetchOne(
    `
   select
    collection_name
   from
    collection_codes
   where
    collection_code = $1
   `,
    [collectionCode],
  );
  if (!coll) {
    try {
      await app.db.exec(
        "insert into collection_codes (collection_code, collection_name) values ($1, $2)",
        [collectionCode, sub.input_collection_name ?? ""],
      );
    } catch (err) {
      if (isUniqueViolation(err)) {
        return jsonResponse(
          {
            message:
              "Your collection code or collection name is already in use. Please choose a unique code and name \n",
          },
          422,
        );
      }
      return jsonResponse(
        { message: `An unexpected error occurred: \n${errMessage(err)}` },
        500,
      );
    }
  }

  // Dates and ints arrive as strings; empty strings mean null. The
  // Python version pushed the raw strings through to Postgres, which
  // does the casting server-side; we do the same via ::casts.
  let baselineDate: string | null = null;
  let dateShift: number | null = null;
  let uidRoot: string | null = null;
  if (sub.input_baseline_date) baselineDate = sub.input_baseline_date;
  if (sub.input_date_shift != null && sub.input_date_shift !== "") {
    if (!/^-?\d+$/.test(sub.input_date_shift)) {
      throw new HttpError(422, "input_date_shift must be an integer");
    }
    dateShift = Number(sub.input_date_shift);
  }
  if (sub.input_uid_root != null) uidRoot = sub.input_uid_root;

  try {
    await app.db.exec(
      `
      insert
          into submissions
          (site_code, collection_code, patient_id_prefix,
           body_part,access_type, baseline_date, date_shift, uid_root)
          values
          ($1, $2, $3, $4, $5, $6::text::timestamp, $7, $8)`,
      [
        siteCode,
        collectionCode,
        sub.input_patient_id_prefix ?? "",
        sub.input_body_part ?? "",
        sub.input_access_type ?? "",
        baselineDate,
        dateShift,
        uidRoot,
      ],
    );
  } catch (err) {
    if (isUniqueViolation(err)) {
      return jsonResponse(
        {
          message:
            "\n Your entry is already in use. Please choose a unique site + collection.",
        },
        422,
      );
    }
    if (isInvalidTextRepresentation(err)) {
      return jsonResponse(
        { message: "Access Type must be one of: public, limited" },
        422,
      );
    }
    throw err;
  }

  return new Response(null, { status: 201 });
}

function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
