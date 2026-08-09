// Ports papi/routes/segs.py.

import type { App } from "../server";
import { pathInt, pathStr } from "../server";
import { HttpError } from "../httpx";
import { fetchJson } from "./common";

/** GET /v1/segs/find_segs_in_activity/{activity_id} */
export interface SegFile {
  file_id: number;
  path: string | null;
}

/** GET /v1/segs/getLatestFileForSop/{sop_instance_uid} */
export interface LatestSopFile {
  file_id: number | null;
}

/** GET /v1/segs/getFORfromfile/{file_id} */
export interface FileFor {
  for_uid: string | null;
}

/** GET /v1/segs/getSeries/{file_id} */
export interface SegSeries {
  series_instance_uid: string | null;
}

export function registerSegs(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "test error, not allowed");
  };
  app.prot("GET", "/v1/segs", notAllowed);
  app.prot("GET", "/v1/segs/", notAllowed);

  app.prot("GET", "/v1/segs/find_segs_in_activity/:activity_id", (ctx) =>
    fetchJson(
      app,
      `
      select
        file_id,
        root_path || '/' || rel_path as path
      from
        file_storage_root natural join file_location
      where file_id in (
        select distinct file_id
        from dicom_file df natural join activity_timepoint_file
        where
        dicom_file_type = 'Segmentation Storage'
        and activity_timepoint_id = (
          select max(activity_timepoint_id) as activity_timepoint_id
          from activity_timepoint
          where activity_id = $1
        )
      );
      `,
      [pathInt(ctx, "activity_id")],
    ),
  );

  app.prot("GET", "/v1/segs/getLatestFileForSop/:sop_instance_uid", (ctx) =>
    fetchJson(
      app,
      `
      select max(file_id) as file_id
      from file_sop_common
      where sop_instance_uid = $1;
      `,
      [pathStr(ctx, "sop_instance_uid")],
    ),
  );

  app.prot("GET", "/v1/segs/getFORfromfile/:file_id", (ctx) =>
    fetchJson(
      app,
      `
      select for_uid from file_for ff where file_id  = $1;
      `,
      [pathInt(ctx, "file_id")],
    ),
  );

  app.prot("GET", "/v1/segs/getSeries/:file_id", (ctx) =>
    fetchJson(
      app,
      `
      select series_instance_uid
      from file_series
      natural join file
      where file_id = $1;
      `,
      [pathInt(ctx, "file_id")],
    ),
  );

  app.prot(
    "PUT",
    "/v1/segs/populate_seg_linkages/:file_id/:seg_id/:linked_sop_instance_uid/:linked_sop_class_uid",
    (ctx) =>
      fetchJson(
        app,
        `
        INSERT INTO public.file_seg_image_linkage
        (file_id, seg_id, linked_sop_instance_uid, linked_sop_class_uid)
        VALUES($1, $2, $3, $4)
        ON CONFLICT (file_id,seg_id) DO UPDATE SET
          linked_sop_instance_uid=EXCLUDED.linked_sop_instance_uid,
          linked_sop_class_uid=EXCLUDED.linked_sop_class_uid;
        `,
        [
          pathInt(ctx, "file_id"),
          pathInt(ctx, "seg_id"),
          pathStr(ctx, "linked_sop_instance_uid"),
          pathStr(ctx, "linked_sop_class_uid"),
        ],
      ),
  );
}
