// Ports papi/routes/deface.py.

import type { App, Ctx, Handler } from "../server";
import { pathInt } from "../server";
import { HttpError, jsonResponse } from "../httpx";
import { decodeJsonBody } from "./common";

/** GET /v1/deface/{defacing_id} — file_nifti_defacing row. */
export interface Defacing {
  file_nifti_defacing_id: number;
  from_nifti_file: number;
  to_nifti_file: number | null;
  three_d_rendered_face: number | null;
  three_d_rendered_face_box: number | null;
  three_d_rendered_defaced: number | null;
  completed_time: string | null;
  comments: string | null;
  success: boolean | null;
  subprocess_invocation_id: number | null;
  error_code: string | null;
}

interface DefaceResult {
  nifti_file_id?: number | null;
  three_d_rendered_face?: number | null;
  three_d_rendered_face_box?: number | null;
  three_d_rendered_defaced?: number | null;
  error_code?: string | null;
}

export function registerDeface(app: App): void {
  app.prot("GET", "/v1/deface/:defacing_id", (ctx) => getDefacing(app, ctx));
  app.prot("POST", "/v1/deface/:defacing_id/complete", defacingComplete(app, true));
  app.prot("POST", "/v1/deface/:defacing_id/error", defacingComplete(app, false));
}

async function getDefacing(app: App, ctx: Ctx): Promise<Response> {
  const row = await app.db.fetchOne<Defacing>(
    `
    select
        file_nifti_defacing_id,
        from_nifti_file,
        to_nifti_file,
        three_d_rendered_face,
        three_d_rendered_face_box,
        three_d_rendered_defaced,
        completed_time::text,
        comments,
        success,
        subprocess_invocation_id,
        error_code
    from
        file_nifti_defacing
    where
        file_nifti_defacing_id = $1
    `,
    [pathInt(ctx, "defacing_id")],
    { completed_time: "tstz" },
  );
  if (!row) {
    throw new HttpError(404, "no such defacing_id");
  }
  return jsonResponse(row);
}

function defacingComplete(app: App, success: boolean): Handler {
  return async (ctx) => {
    const id = pathInt(ctx, "defacing_id");
    const body = await decodeJsonBody<DefaceResult>(ctx.req);

    await app.db.exec(
      `
      update
          file_nifti_defacing
      set
          to_nifti_file = $2,
          three_d_rendered_face = $3,
          three_d_rendered_face_box = $4,
          three_d_rendered_defaced = $5,
          error_code = $6,
          success = ${success},
          completed_time = now()
      where
          file_nifti_defacing_id = $1
      `,
      [
        id,
        body.nifti_file_id ?? null,
        body.three_d_rendered_face ?? null,
        body.three_d_rendered_face_box ?? null,
        body.three_d_rendered_defaced ?? null,
        body.error_code ?? null,
      ],
    );
    return jsonResponse({ status: "success" });
  };
}
