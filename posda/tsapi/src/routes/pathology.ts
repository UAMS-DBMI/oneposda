// Ports papi/routes/pathology.py.
//
// Note on the PUT endpoints: the Python handlers run their
// INSERT/UPDATE via db.fetch and then require at least one returned
// row. Statements without a RETURNING clause never return rows, so
// those endpoints perform their write and then respond 422 "Error
// updating edit status" even on success. That behavior is preserved
// here because existing clients depend on it.

import type { App, Ctx, Handler } from "../server";
import { doc } from "../openapi";
import { pathInt, pathStr } from "../server";
import { HttpError, jsonResponse } from "../httpx";
import type { Convs } from "../pgconvert";
import { fetchJson, fetchOneJson } from "./common";

/** A bare file_id, the element type of several pathology lookups. */
export interface PathologyFileID {
  file_id: number;
}

/** GET /v1/pathology/find_edits/{file_id} */
export interface PathologyEdit {
  pathology_edit_queue_id: number;
  edit_type: string | null;
  edit_details: string | null;
}

/** GET /v1/pathology/find_relpath/{file_id} */
export interface PathologyRelPath {
  root_path: string | null;
  rel_path: string | null;
}

/** GET /v1/pathology/getActEdits/{act_id} */
export interface PathologyEditCount {
  file_id: number;
  count: number;
}

/** GET /v1/pathology/getActEditsByPVRID/{pvr_id} — the file_id column is
 * aliased to "file" by the query. */
export interface PathologyEditCountByPVR {
  file: number;
  count: number;
}

/** GET /v1/pathology/mapping/{file_id} */
export interface PathologyPatientMapping {
  patient_id: string | null;
}

/** GET /v1/pathology/preview_file_name/{pathid} */
export interface PathologyPreviewFile {
  file_name: string | null;
  good_status: boolean | null;
}

/** GET /v1/pathology/preview/{pathid}/{gammaIndex} */
export interface PathologyPreviewFileID {
  preview_file_id: number;
}

/** GET /v1/pathology/start/{vr_id} */
export interface PathologyReviewFileID {
  path_file_id: number;
}

export function registerPathology(app: App): void {
  const pathQueryInt = (param: string, sql: string, convs?: Convs): Handler => {
    return (ctx) => fetchJson(app, sql, [pathInt(ctx, param)], convs);
  };

  app.prot(
    "GET",
    "/v1/pathology/start/:vr_id",
    pathQueryInt(
      "vr_id",
      `
      select distinct
        path_file_id
      from
        pathology_visual_review_files
      where
        pathology_visual_review_instance_id = $1
      order by path_file_id;
      `,
    ),
    doc<PathologyReviewFileID[]>({
      summary: "Get Files For Review",
      params: {
        vr_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/preview_file_name/:pathid",
    pathQueryInt(
      "pathid",
      `
       select
          file_name, good_status
      from
          file_import a
          left join pathology_visual_review_status b on a.file_id = b.path_file_id
      where
          a.file_id = $1
           `,
    ),
    doc<PathologyPreviewFile[]>({
      summary: "Get Filename",
      params: {
        pathid: { type: "integer" },
      },
    }),
  );

  app.prot("GET", "/v1/pathology/preview/:pathid/:gammaIndex", (ctx) =>
    fetchJson(
      app,
      `
      select
       distinct preview_file_id
      from
          pathology_visual_review_preview_files
      where
          path_file_id = $1
          and gammaindex = $2
      `,
      [pathInt(ctx, "pathid"), pathInt(ctx, "gammaIndex")],
    ),
    doc<PathologyPreviewFileID[]>({
      summary: "Get Previews",
      params: {
        pathid: { type: "integer" },
        gammaIndex: { type: "integer" },
      },
    }),
  );

  const queuedRemovals: Handler = () =>
    fetchJson(
      app,
      `
       select
        file_id
      from pathology_edit_queue p
      where p.status = 'waiting' and p.edit_type = '4';
      `,
    );
  app.prot("GET", "/v1/pathology/get_queued_removals", queuedRemovals,
    doc<PathologyFileID[]>({
      summary: "Get Queued Removals",
    }),
  );
  app.prot("GET", "/v1/pathology/get_queued_removals/", queuedRemovals,
    doc<PathologyFileID[]>({
      summary: "Get Queued Removals",
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/getActEdits/:act_id",
    pathQueryInt(
      "act_id",
      `
      select
          atf.file_id, count(p.status)
      from activity_timepoint_file atf
          left join pathology_edit_queue p on atf.file_id = p.file_id and p.status = 'waiting'
      where atf.activity_timepoint_id =
             ( select
                  max(activity_timepoint_id) as activity_timepoint_id
              from
                  activity_timepoint
              where
                  activity_id = $1 )
      group by atf.file_id
      `,
      { count: "int8" },
    ),
    doc<PathologyEditCount[]>({
      summary: "Get Path Edits On Act",
      params: {
        act_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/getActEditsByPVRID/:pvr_id",
    pathQueryInt(
      "pvr_id",
      `
      select
          atf.file_id as file, count(p.status) as count
      from activity_timepoint_file atf
          left join pathology_edit_queue p on atf.file_id = p.file_id and p.status = 'waiting'
      where atf.activity_timepoint_id =
         (select
              max(activity_timepoint_id) as activity_timepoint_id
          from
              activity_timepoint
          where
              activity_id =
              (select
                  activity_creation_id
              from pathology_visual_review_instance pvri
              where pvri.pathology_visual_review_instance_id = $1 ))
       group by atf.file_id;
      `,
      { count: "int8" },
    ),
    doc<PathologyEditCountByPVR[]>({
      summary: "Get Path Edits Pvr Instance",
      params: {
        pvr_id: { type: "integer" },
      },
    }),
  );

  app.prot("PUT", "/v1/pathology/set_edit/:pathid/:good_status/:user", (ctx) =>
    pathEditWrite(
      app,
      `
      INSERT INTO pathology_visual_review_status
      VALUES($1 , $2, $3, now());
      `,
      [
        pathInt(ctx, "pathid"),
        parsePathBool(pathStr(ctx, "good_status")),
        pathStr(ctx, "user"),
      ],
    ),
    doc({
      summary: "Set Edit",
      params: {
        pathid: { type: "integer" },
      },
    }),
  );

  const pathEditById = (sql: string): Handler => {
    return (ctx) => pathEditWrite(app, sql, [pathInt(ctx, "pathid")]);
  };

  app.prot(
    "PUT",
    "/v1/pathology/remM/:pathid",
    pathEditById(`
      INSERT INTO pathology_edit_queue
      (file_id,edit_type, edit_details, status)
      VALUES($1 , 1, NULL, 'waiting');
      `),
    doc({
      summary: "Remm",
      params: {
        pathid: { type: "integer" },
      },
    }),
  );

  app.prot("PUT", "/v1/pathology/redact/:dims/:pathid", (ctx) =>
    pathEditWrite(
      app,
      `
      INSERT INTO pathology_edit_queue
      (file_id,edit_type, edit_details, status)
      VALUES($1 , 5, $2, 'waiting');
      `,
      [pathInt(ctx, "pathid"), pathStr(ctx, "dims")],
    ),
    doc({
      summary: "Redact",
      params: {
        pathid: { type: "integer" },
      },
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/remL/:pathid",
    pathEditById(`
      INSERT INTO pathology_edit_queue
      (file_id,edit_type, edit_details, status)
      VALUES($1 , 2, NULL, 'waiting');
      `),
    doc({
      summary: "Reml",
      params: {
        pathid: { type: "integer" },
      },
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/removeF/:pathid",
    pathEditById(`
      INSERT INTO pathology_edit_queue
      (file_id,edit_type, edit_details, status)
      VALUES($1 , 4, NULL, 'waiting');
      `),
    doc({
      summary: "Remf",
      params: {
        pathid: { type: "integer" },
      },
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/editMeta/:pathid",
    pathEditById(`
      INSERT INTO pathology_edit_queue
      (file_id,edit_type, edit_details, status)
      VALUES($1 , 3, 'imgdesc', 'waiting');
      `),
    doc({
      summary: "Editm",
      params: {
        pathid: { type: "integer" },
      },
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/cancelEdit/:pathid",
    pathEditById(`
      update pathology_edit_queue
      set status = 'canceled'
      where
      status = 'waiting'
      and file_id = $1
      `),
    doc({
      summary: "Canceledit",
      params: {
        pathid: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/review/:vr_id",
    pathQueryInt(
      "vr_id",
      `
    select distinct
        d.file_name,
        good_status
    from
        pathology_visual_review_preview_files b
        left join file_import d on d.file_id = b.path_file_id
        left join pathology_visual_review_status c on b.path_file_id = c.path_file_id
    where
        pathology_visual_review_instance_id = $1
      `,
    ),
    doc({
      summary: "Review",
      params: {
        vr_id: { type: "integer" },
      },
    }),
  );

  app.prot("PUT", "/v1/pathology/copymapping/:oldfile_id/:newfile_id", (ctx) =>
    fetchJson(
      app,
      `
          insert into pathology_patient_mapping
          (file_id,patient_id,collection_name,site_name,study_name,image_id,clinical_trial_subject_id)
      select
         $2, patient_id,collection_name,site_name,study_name,image_id,clinical_trial_subject_id
      from
          pathology_patient_mapping a
      where
          a.file_id = $1;
           `,
      [pathInt(ctx, "oldfile_id"), pathInt(ctx, "newfile_id")],
    ),
    doc({
      summary: "Copymapping",
      params: {
        oldfile_id: { type: "integer" },
        newfile_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/mapping/:file_id",
    pathQueryInt(
      "file_id",
      `
       select
          patient_id
      from
          pathology_patient_mapping a
      where
          a.file_id = $1
           `,
    ),
    doc<PathologyPatientMapping[]>({
      summary: "Get Mapping",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/setmapping/:file_id/:patient_id/:collection_name/:site_name/:study_name/:image_id/:clinical_trial_subject_id",
    (ctx) =>
      fetchJson(
        app,
        `
      insert into pathology_patient_mapping
          (file_id,patient_id,collection_name,site_name,study_name,image_id,clinical_trial_subject_id)
      VALUES
          ($1,$2,$3,$4,$5,$6,$7)
      ON CONFLICT (file_id) DO UPDATE
      set
          patient_id=$2,
          collection_name=$3,
          site_name=$4,
          study_name=$5,
          image_id=$6,
          clinical_trial_subject_id=$7
           `,
        [
          pathInt(ctx, "file_id"),
          pathStr(ctx, "patient_id"),
          pathStr(ctx, "collection_name"),
          pathStr(ctx, "site_name"),
          pathStr(ctx, "study_name"),
          pathStr(ctx, "image_id"),
          pathStr(ctx, "clinical_trial_subject_id"),
        ],
      ),
    doc({
      summary: "Setmapping",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/image_desc/:file_id",
    pathQueryInt(
      "file_id",
      `
      select
          layer_id, image_desc
      from
          pathology_image_description a
      where
          a.file_id = $1
           `,
    ),
    doc({
      summary: "Get Image Desc",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );

  app.prot("GET", "/v1/pathology/getcount", () =>
    // Python counts a module-level dict that is never written to.
    jsonResponse(0),
    doc<number>({
      summary: "Get Current Count",
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/find_files/:activity_id",
    pathQueryInt(
      "activity_id",
      `
      select f.file_id from file f join activity_timepoint_file atf  on f.file_id = atf.file_id
          where atf.activity_timepoint_id in (
              select
                  max(activity_timepoint_id) as activity_timepoint_id
              from
                  activity_timepoint
              where
                  activity_id = $1
            );
      `,
    ),
    doc<PathologyFileID[]>({
      summary: "Find Files",
      params: {
        activity_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/find_edits/:file_id",
    pathQueryInt(
      "file_id",
      `
   select pathology_edit_queue_id, edit_type, edit_details
          from pathology_edit_queue
           where
               file_id = $1
               and status = 'waiting'
      `,
    ),
    doc<PathologyEdit[]>({
      summary: "Find Edits",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/find_relpath/:file_id",
    pathQueryInt(
      "file_id",
      `
    select root_path, rel_path
    from file_location f
    natural join file_storage_root fsr
    where f.file_id = $1
     `,
    ),
    doc<PathologyRelPath[]>({
      summary: "Find Relpath",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );

  app.prot("PATCH", "/v1/pathology/completeEdit/:edit_id", async (ctx) => {
    const rows = await app.db.fetch(
      `
      update pathology_edit_queue set status = 'complete' where pathology_edit_queue_id = $1 returning pathology_edit_queue_id;
      `,
      [pathInt(ctx, "edit_id")],
    );
    if (rows.length < 1) {
      throw new HttpError(422, "Complete Edit: Error updating edit status");
    }
    return jsonResponse({ status: "success" });
  },
    doc({
      summary: "Completeedit",
      params: {
        edit_id: { type: "integer" },
      },
    }),
  );

  app.prot("GET", "/v1/pathology/getXfiles/:import_id/:file_type", (ctx) =>
    fetchJson(
      app,
      String.raw`
      select
          file_id
      from
          file_import
      where
          import_event_id = $1
          AND SUBSTRING(file_name FROM '\.([^\.]*)$') = $2;
      `,
      [pathInt(ctx, "import_id"), pathStr(ctx, "file_type")],
    ),
    doc<PathologyFileID[]>({
      summary: "Getxfiles",
      params: {
        import_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/pathology/get_files_from_import/:import_id",
    pathQueryInt(
      "import_id",
      `
      select
          file_id
      from
          file_import
      where
          import_event_id = $1;
      `,
    ),
    doc<PathologyFileID[]>({
      summary: "Get Files From Import",
      params: {
        import_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/create_path_activity/:activity_name/:user",
    (ctx) =>
      fetchJson(
        app,
        `
        insert into activity (
            brief_description,
            when_created,
            who_created
        ) values (
         $1 ,now(), $2)
         returning activity_id;
        `,
        [pathStr(ctx, "activity_name"), pathStr(ctx, "user")],
      ),
    doc({
      summary: "Create Path Activit",
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/create_path_activity_timepoint/:activity_id/:user",
    (ctx) =>
      fetchJson(
        app,
        `
        insert into activity_timepoint(
            activity_id,
            when_created,
            who_created,
            comment,
            creating_user
        ) values (
            $1, now(), $2, 'Post Edit Pathology TP', $2)
        returning activity_timepoint_id;
        `,
        [pathInt(ctx, "activity_id"), pathStr(ctx, "user")],
      ),
    doc({
      summary: "Create Path Activity Timepoint",
      params: {
        activity_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/add_file_to_path_activity_timepoint/:atf_id/:file_id",
    (ctx) =>
      fetchJson(
        app,
        `
        insert into activity_timepoint_file(
             activity_timepoint_id,
             file_id
            ) values (
              $1, $2)
        returning file_id;
        `,
        [pathInt(ctx, "atf_id"), pathInt(ctx, "file_id")],
      ),
    doc({
      summary: "Add File To Path Activity Timepoint",
      params: {
        atf_id: { type: "integer" },
        file_id: { type: "integer" },
      },
    }),
  );

  const pathBulkEdit = (editType: string): Handler => {
    const sql = `
   INSERT INTO pathology_edit_queue
            (file_id,edit_type, edit_details, status)
          select
              file_id,  ${editType}, NULL, 'waiting'
          from activity_timepoint_file atf
          where atf.activity_timepoint_id =
                 ( select
                      max(activity_timepoint_id) as activity_timepoint_id
                  from
                      activity_timepoint att
                      join pathology_visual_review_instance pf
                      on att.activity_id = pf.activity_creation_id
                      where pf.pathology_visual_review_instance_id = $1 );
    `;
    return (ctx) =>
      pathEditWrite(app, sql, [
        pathInt(ctx, "pathology_visual_review_instance_id"),
      ]);
  };

  app.prot(
    "PUT",
    "/v1/pathology/bulkMacro/:pathology_visual_review_instance_id",
    pathBulkEdit("1"),
    doc({
      summary: "Editbulkmacro",
      params: {
        pathology_visual_review_instance_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "PUT",
    "/v1/pathology/bulkLabel/:pathology_visual_review_instance_id",
    pathBulkEdit("2"),
    doc({
      summary: "Editbulklabel",
      params: {
        pathology_visual_review_instance_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "PUT",
    "/v1/pathology/bulkMeta/:pathology_visual_review_instance_id",
    pathBulkEdit("3"),
    doc({
      summary: "Editbulkmeta",
      params: {
        pathology_visual_review_instance_id: { type: "integer" },
      },
    }),
  );

  app.prot("PUT", "/v1/pathology/recordPathDBresponse/:file_id/:node_id", (ctx) =>
    pathEditWrite(
      app,
      `
      INSERT INTO pathology_path_db_linkage
      (file_id,node_id,upload_time)
      VALUES($1 , $2, now());
      `,
      [pathInt(ctx, "file_id"), pathStr(ctx, "node_id")],
    ),
    doc({
      summary: "Recordpathdbresponse",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "PUT",
    "/v1/pathology/insert_image_meta/:file_id/:format/:modality/:protocol/:manufacturer/:model/:xResolution/:yResolution/:resolutionUnit/:magnification/:mppx/:mppy/:image_volume_width/:image_volume_height/:reference_pixel_physical_value_x/:reference_pixel_physical_value_y",
    (ctx) => insertImageMeta(app, ctx),
    doc({
      summary: "Insert Image Meta",
      params: {
        file_id: { type: "integer" },
      },
    }),
  );
}

/**
 * Perform a write and then respond exactly like the Python
 * `len(record) < 1` check: statements without RETURNING yield no rows,
 * so the response is a 422 even though the write succeeded.
 */
async function pathEditWrite(
  app: App,
  sql: string,
  args: unknown[],
): Promise<Response> {
  const rows = await app.db.fetch(sql, args);
  if (rows.length < 1) {
    throw new HttpError(422, "Error updating edit status");
  }
  return jsonResponse({ status: "success" });
}

function parsePathBool(s: string): boolean {
  switch (s) {
    case "1":
    case "true":
    case "True":
    case "yes":
    case "on":
      return true;
    case "0":
    case "false":
    case "False":
    case "no":
    case "off":
      return false;
  }
  throw new HttpError(422, "good_status must be a boolean");
}

function parsePathFloat(ctx: Ctx, name: string): number {
  const raw = ctx.params[name] ?? "";
  const f = Number(raw);
  if (raw === "" || Number.isNaN(f)) {
    throw new HttpError(422, `path parameter "${name}" must be a number`);
  }
  return f;
}

async function insertImageMeta(app: App, ctx: Ctx): Promise<Response> {
  const fileId = pathInt(ctx, "file_id");
  const floats: Record<string, number> = {};
  for (const name of [
    "mppx",
    "mppy",
    "image_volume_width",
    "image_volume_height",
    "reference_pixel_physical_value_x",
    "reference_pixel_physical_value_y",
  ]) {
    floats[name] = parsePathFloat(ctx, name);
  }

  return fetchOneJson(
    app,
    `
    INSERT INTO public.pathology_image_meta
    (file_id,
    format,
    modality,
    protocol,
    manufacturer,
    model,
    xresolution,
    yresolution,
    resolutionunit,
    magnification,
    mppx,
    mppy,
    image_volume_width,
    image_volume_height,
    reference_pixel_physical_value_x,
    reference_pixel_physical_value_y)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
    RETURNING file_id;
    `,
    [
      fileId,
      pathStr(ctx, "format"),
      pathStr(ctx, "modality"),
      pathStr(ctx, "protocol"),
      pathStr(ctx, "manufacturer"),
      pathStr(ctx, "model"),
      pathStr(ctx, "xResolution"),
      pathStr(ctx, "yResolution"),
      pathStr(ctx, "resolutionUnit"),
      pathStr(ctx, "magnification"),
      floats.mppx,
      floats.mppy,
      floats.image_volume_width,
      floats.image_volume_height,
      floats.reference_pixel_physical_value_x,
      floats.reference_pixel_physical_value_y,
    ],
  );
}
