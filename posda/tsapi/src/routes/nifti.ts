// Ports papi/routes/nifti.py.

import type { App, Ctx } from "../server";
import { doc, type OrEmptyObject } from "../openapi";
import { pathInt, pathStr } from "../server";
import { HttpError, jsonResponse } from "../httpx";
import { isForeignKeyViolation } from "../db";
import { fetchFirstColumn } from "./common";

/** GET /v1/nifti/{nifti_id} */
export interface NiftiDetails {
  file_id: number;
  file_name: string | null;
  root_path: string | null;
  rel_path: string | null;
  is_zipped: boolean | null;
  import_path: string;
  import_name: string;
  download_path: string;
  posda_path: string;
}

export function registerNifti(app: App): void {
  app.prot("GET", "/v1/nifti/:nifti_id", (ctx) => getNiftiDetails(app, ctx),
    doc<OrEmptyObject<NiftiDetails>>({
      summary: "Get Nifti Details",
      description: "Return details about the given Nifti File",
      params: {
        nifti_id: { type: "integer" },
      },
    }),
  );
  app.prot("POST", "/v1/nifti/:nifti_id/set_status/:review_status", (ctx) =>
    setNiftiStatus(app, ctx),
    doc({
      summary: "Set Status",
      description: "Update/Set Nifti review status",
      params: {
        nifti_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/nifti/visualreview/:nifti_visual_review_instance_id",
    (ctx) =>
      fetchFirstColumn(
        app,
        `
        select
            nifti_file_id
        from
            nifti_visual_review_files
                natural left join nifti_visual_review_status
        where
            nifti_visual_review_instance_id = $1
            and nifti_visual_review_status.nifti_file_id is null
        order by 1
        `,
        [pathInt(ctx, "nifti_visual_review_instance_id")],
      ),
    doc({
      summary: "Get For Visualreview",
      description: "Return list of all Files in this Nifti VR",
      params: {
        nifti_visual_review_instance_id: { type: "integer" },
      },
    }),
  );
}

async function getNiftiDetails(app: App, ctx: Ctx): Promise<Response> {
  const niftiId = pathInt(ctx, "nifti_id");
  const row = await app.db.fetchOne(
    `
    select fn.file_id,
           fi.file_name,
           fsr.root_path,
           fl.rel_path,
           fn.is_zipped
    from file_nifti fn
    natural join file_location fl
    natural join file_storage_root fsr
    left join file_import fi
    on fn.file_id = fi.file_id
    and fi.import_event_id = (
        select max(import_event_id)
        from file_import fi_sub
        where fi_sub.file_id = fn.file_id)
    where fn.file_id = $1
    `,
    [niftiId],
  );
  if (!row) return jsonResponse({});

  const fileName = typeof row.file_name === "string" ? row.file_name : "";
  const slash = fileName.lastIndexOf("/");
  const details: NiftiDetails = {
    ...(row as object as Omit<NiftiDetails, "import_path" | "import_name" | "download_path" | "posda_path">),
    import_path: slash >= 0 ? fileName.slice(0, slash) : "",
    import_name: slash >= 0 ? fileName.slice(slash + 1) : fileName,
    download_path: `/papi/v1/files/${niftiId}/data`,
    posda_path: `${row.root_path ?? ""}/${row.rel_path ?? ""}`,
  };
  return jsonResponse(details);
}

async function setNiftiStatus(app: App, ctx: Ctx): Promise<Response> {
  const niftiId = pathInt(ctx, "nifti_id");
  try {
    await app.db.exec(
      `
      insert into nifti_visual_review_status (nifti_file_id, review_status, reviewing_user, review_time)
      values ($1, $2, $3, now())
      on conflict (nifti_file_id)
      do update set
          review_status = EXCLUDED.review_status,
          reviewing_user = EXCLUDED.reviewing_user,
          review_time = now();
      `,
      [niftiId, pathStr(ctx, "review_status"), ctx.user!.username],
    );
  } catch (err) {
    if (isForeignKeyViolation(err)) {
      throw new HttpError(422, "Invalid File ID supplied");
    }
    throw new HttpError(500, "An unexpected error occurred");
  }
  return jsonResponse({ message: "Nifti review status updated successfully" });
}
