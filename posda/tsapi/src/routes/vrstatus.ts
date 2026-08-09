// Ports papi/routes/vrstatus.py.

import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathInt, pathStr } from "../server";
import { HttpError, jsonResponse } from "../httpx";
import { isForeignKeyViolation } from "../db";
import { fetchJson } from "./common";

/** GET /v1/vrstatus/find_vr_ready_to_begin_status_updates */
export interface VrReadyInstance {
  visual_review_instance_id: number;
}

/** GET .../get_reviewed_percentage_for_vr and .../get_visible_bads_for_vr */
export interface VrSummary {
  summary: string | null;
}

export function registerVRStatus(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "test error, not allowed");
  };
  app.prot("GET", "/v1/vrstatus", notAllowed,
    doc({
      summary: "Test",
    }),
  );
  app.prot("GET", "/v1/vrstatus/", notAllowed,
    doc({
      summary: "Test",
    }),
  );

  app.prot("GET", "/v1/vrstatus/find_vr_ready_to_begin_status_updates", () =>
    fetchJson(
      app,
      `
      select
          b.visual_review_instance_id
      from
        activity_task_status a
        join visual_review_instance b
            on b.subprocess_invocation_id = a.subprocess_invocation_id
      where
          b.visual_review_reason = 'Activity Id: ' || a.activity_id
          and a.manual_update = true;
      `,
    ),
    doc<VrReadyInstance[]>({
      summary: "Find Vr Ready To Begin Status Updates",
    }),
  );

  app.prot(
    "GET",
    "/v1/vrstatus/get_reviewed_percentage_for_vr/:visual_review_instance_id",
    (ctx) =>
      fetchJson(
        app,
        `
        select
            ('' || processing_status::text || ' ' || ((count(*)/(select  sum(c) as t from (select count(*) as c from image_equivalence_class where visual_review_instance_id = $1 ) as sum_table)::float) * 100.0)::int || '%')::text as summary
        from
            image_equivalence_class
        where
            visual_review_instance_id = $1
        group by
            processing_status
        `,
        [pathInt(ctx, "visual_review_instance_id")],
      ),
    doc({
      summary: "Get Reviewed Percentage For Vr",
      params: {
        visual_review_instance_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/vrstatus/update_activity_status/:visual_review_instance_id/:new_status",
    (ctx) =>
      fetchJson(
        app,
        `
        update
            activity_task_status
        set
            status_text = $2
        from
             visual_review_instance b
        where
            activity_task_status.manual_update = true
            and b.visual_review_instance_id = $1
            and b.visual_review_reason = 'Activity Id: ' || activity_task_status.activity_id
            and b.subprocess_invocation_id = activity_task_status.subprocess_invocation_id;
        `,
        [
          pathInt(ctx, "visual_review_instance_id"),
          pathStr(ctx, "new_status"),
        ],
      ),
    doc({
      summary: "Update Activity Status",
      params: {
        visual_review_instance_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/vrstatus/get_visible_bads_for_vr/:visual_review_instance_id",
    (ctx) =>
      fetchJson(
        app,
        `
        select
            'Reviewed 100% , ' || count(file_id) || ' files need to be set to Bad and hidden to continue.' as summary
        from
            image_equivalence_class a
            natural join image_equivalence_class_input_image c
            natural join ctp_file d
        where
            visual_review_instance_id = $1
            and a.review_status <> 'Good'
            and ( (a.review_status = 'Bad') or a.review_status = 'Blank' or a.review_status = 'Other' or a.review_status = 'Scout' or a.review_status = 'Flagged')
        `,
        [pathInt(ctx, "visual_review_instance_id")],
      ),
    doc({
      summary: "Get Visible Bads For Vr",
      params: {
        visual_review_instance_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/vrstatus/finish_activity_status/:visual_review_instance_id",
    (ctx) =>
      fetchJson(
        app,
        `
        update
            activity_task_status
        set
            manual_update = false
        from
             visual_review_instance b
        where
            activity_task_status.manual_update = true
            and b.visual_review_instance_id = $1
            and b.visual_review_reason = 'Activity Id: ' || activity_task_status.activity_id
            and b.subprocess_invocation_id = activity_task_status.subprocess_invocation_id;
        `,
        [pathInt(ctx, "visual_review_instance_id")],
      ),
    doc({
      summary: "Finish Activity Status",
      params: {
        visual_review_instance_id: { type: "integer" },
      },
    }),
  );

  app.prot("POST", "/v1/vrstatus/:iec/set_status/:review_status", (ctx) =>
    setIECReviewStatus(app, ctx),
    doc({
      summary: "Set Status",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
}

async function setIECReviewStatus(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");
  try {
    await app.db.exec(
      `
      update image_equivalence_class
      set processing_status = 'Reviewed',
          review_status = $1,
          update_user = $2,
          update_date = now()
      where image_equivalence_class_id = $3
      `,
      [pathStr(ctx, "review_status"), ctx.user!.username, iec],
    );
  } catch (err) {
    if (isForeignKeyViolation(err)) {
      throw new HttpError(422, "Invalid IEC supplied");
    }
    console.error(`An error occurred: ${err}`);
    throw new HttpError(500, "An unexpected error occurred");
  }
  return jsonResponse({ message: "IEC review status updated successfully" });
}
