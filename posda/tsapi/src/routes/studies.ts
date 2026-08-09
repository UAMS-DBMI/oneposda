// Ports papi/routes/studies.py.

import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathStr } from "../server";
import { HttpError, InternalError, jsonResponse } from "../httpx";
import { fetchJson } from "./common";

/** GET /v1/studies/{study_instance_uid} */
export interface StudyDetail {
  study_date: string | null;
  study_time: string | null;
  series_count: number;
}

/** GET /v1/studies/{study_instance_uid}/series */
export interface StudySeries {
  series_instance_uid: string | null;
}

export function registerStudies(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "listing all studies is not allowed");
  };
  app.prot("GET", "/v1/studies", notAllowed,
    doc({
      summary: "Get All Studies",
    }),
  );
  app.prot("GET", "/v1/studies/", notAllowed,
    doc({
      summary: "Get All Studies",
    }),
  );

  app.prot("GET", "/v1/studies/:study_instance_uid", (ctx) =>
    getSingleStudy(app, ctx),
    doc<StudyDetail>({
      summary: "Get Single Study",
    }),
  );
  app.prot("GET", "/v1/studies/:study_instance_uid/series", (ctx) =>
    fetchJson(
      app,
      `
      select distinct
          series_instance_uid
      from file_study
      natural join file_series
      where study_instance_uid = $1
      `,
      [pathStr(ctx, "study_instance_uid")],
    ),
    doc<StudySeries[]>({
      summary: "Get All Series",
    }),
  );
}

async function getSingleStudy(app: App, ctx: Ctx): Promise<Response> {
  const row = await app.db.fetchOne<StudyDetail>(
    `
    select
        study_date,
        study_time::text,
        count(distinct series_instance_uid) as series_count
    from file_study
    natural join file_series
    where study_instance_uid = $1
    group by
        study_date,
        study_time
    `,
    [pathStr(ctx, "study_instance_uid")],
    { study_date: "date", series_count: "int8" },
  );
  if (!row) {
    // Python would raise constructing StudyDetail from an empty
    // record, which surfaces as a 500.
    throw new InternalError();
  }
  return jsonResponse(row);
}
