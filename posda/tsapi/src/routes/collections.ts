// Ports papi/routes/collections.py.

import type { App, Ctx } from "../server";
import { doc, type OrEmpty } from "../openapi";
import { pathStr, queryStr } from "../server";
import { fetchJson, fetchOneJson } from "./common";

/** GET /v1/collections */
export interface CollectionSummary {
  collection: string | null;
  site: string | null;
  file_count: number;
}

/** GET /v1/collections/{collection_name}/{site_name} */
export interface CollectionInfo extends CollectionSummary {
  patient_count: number;
}

/** GET .../patients */
export interface PatientName {
  patient: string | null;
}

/** GET .../patients/{patient_id} */
export interface PatientDetail {
  patient: string | null;
  patient_id: string | null;
  patient_sex: string | null;
  patient_ethnic_group: string | null;
  comments: (string | null)[] | null;
  file_count: number;
  study_count: number;
}

/** GET .../patients/{patient_id}/studies */
export interface PatientStudy {
  collection: string | null;
  site: string | null;
  patient: string | null;
  study_instance_uid: string | null;
}

export function registerCollections(app: App): void {
  app.prot("GET", "/v1/collections", (ctx) => getAllCollections(app, ctx),
    doc<CollectionSummary[]>({
      summary: "Get All Collections",
      description: "Get a list of collections in this Posda instance.\n\nIf collection is set, it will return only collections with that exact name.\nIf site is set, it will return only collections with that exact site name.\n\nIf both are set, site is ignored.",
      params: {
        collection: { in: "query" },
        site: { in: "query" },
      },
    }),
  );
  app.prot("GET", "/v1/collections/", (ctx) => getAllCollections(app, ctx),
    doc<CollectionSummary[]>({
      summary: "Get All Collections",
      description: "Get a list of collections in this Posda instance.\n\nIf collection is set, it will return only collections with that exact name.\nIf site is set, it will return only collections with that exact site name.\n\nIf both are set, site is ignored.",
      params: {
        collection: { in: "query" },
        site: { in: "query" },
      },
    }),
  );

  app.prot("GET", "/v1/collections/:collection_name/:site_name", (ctx) =>
    fetchOneJson(
      app,
      `
      select
          project_name as collection,
          site_name as site,
          count(file_id) as file_count,
          count(distinct patient_name) as patient_count
      from ctp_file
      natural join file_patient
      where project_name = $1
        and site_name = $2
      group by
          project_name, site_name
      `,
      [pathStr(ctx, "collection_name"), pathStr(ctx, "site_name")],
      { file_count: "int8", patient_count: "int8" },
    ),
    doc<OrEmpty<CollectionInfo>>({
      summary: "Get Collection Info",
    }),
  );

  app.prot(
    "GET",
    "/v1/collections/:collection_name/:site_name/patients",
    (ctx) =>
      fetchJson(
        app,
        `
        select distinct
            patient_name as patient
        from ctp_file
        natural join file_patient
        where project_name = $1
          and site_name = $2
        `,
        [pathStr(ctx, "collection_name"), pathStr(ctx, "site_name")],
      ),
    doc<PatientName[]>({
      summary: "Get All Patients",
    }),
  );

  app.prot(
    "GET",
    "/v1/collections/:collection_name/:site_name/patients/:patient_id",
    (ctx) =>
      fetchOneJson(
        app,
        `
        select
            patient_name as patient,
            max(patient_id) as patient_id,
            max(sex) as patient_sex,
            max(ethnic_group) as patient_ethnic_group,
            array_agg(distinct comments) as comments,
            count(file_id) as file_count,
            count(distinct study_instance_uid) as study_count
        from ctp_file
        natural join file_patient
        natural join file_study
        where project_name = $1
          and site_name = $2
          and patient_name = $3
        group by patient_name
        `,
        [
          pathStr(ctx, "collection_name"),
          pathStr(ctx, "site_name"),
          pathStr(ctx, "patient_id"),
        ],
        { file_count: "int8", study_count: "int8" },
      ),
    doc<OrEmpty<PatientDetail>>({
      summary: "Get Single Patient",
    }),
  );

  app.prot(
    "GET",
    "/v1/collections/:collection_name/:site_name/patients/:patient_id/studies",
    (ctx) =>
      fetchJson(
        app,
        `
        select distinct
            project_name as collection,
            site_name as site,
            patient_name as patient,
            study_instance_uid
        from ctp_file
        natural join file_patient
        natural join file_study
        where project_name = $1
          and site_name = $2
          and patient_name = $3
        `,
        [
          pathStr(ctx, "collection_name"),
          pathStr(ctx, "site_name"),
          pathStr(ctx, "patient_id"),
        ],
      ),
    doc<PatientStudy[]>({
      summary: "Get All Studies",
    }),
  );
}

async function getAllCollections(app: App, ctx: Ctx): Promise<Response> {
  const convs = { file_count: "int8" } as const;
  // If both filters are set, site is ignored (same as Python).
  const collection = queryStr(ctx, "collection", "");
  if (collection !== "") {
    return fetchJson(
      app,
      `select project_name as collection, site_name as site, count(file_id) as file_count
       from ctp_file where project_name = $1 group by project_name, site_name`,
      [collection],
      convs,
    );
  }
  const site = queryStr(ctx, "site", "");
  if (site !== "") {
    return fetchJson(
      app,
      `select project_name as collection, site_name as site, count(file_id) as file_count
       from ctp_file where site_name = $1 group by project_name, site_name`,
      [site],
      convs,
    );
  }
  return fetchJson(
    app,
    `select project_name as collection, site_name as site, count(file_id) as file_count
     from ctp_file group by project_name, site_name`,
    [],
    convs,
  );
}
