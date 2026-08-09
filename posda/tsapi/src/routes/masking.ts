// Ports papi/routes/masking.py.

import type { App, Ctx, Handler } from "../server";
import { doc } from "../openapi";
import { pathInt, queryBool, queryInt } from "../server";
import { HttpError, errNoRecords, jsonResponse } from "../httpx";
import { isForeignKeyViolation, isUniqueViolation } from "../db";
import { pyJson } from "../pyjson";
import { decodeJsonBody, fetchFirstColumn, firstColumn } from "./common";
import { appendFilter, vrExists } from "./visualreviews";
import { iecFrameList } from "./iecs";
import { streamZip } from "../archive";

/** masking rows (masking_parameters is jsonb, returned as raw text). */
export interface Masking {
  image_equivalence_class_id: number;
  masking_parameters: string | null;
  masking_status: string;
  import_event_id: number | null;
  masking_exit_code: number | null;
}

/**
 * GET /v1/masking/{iec}. An IEC with no masking row still gets a
 * response — just `{"history": [...]}`, matching dict() of an empty
 * fetch_one result — so everything but the history is optional.
 */
export type MaskingDetails = Partial<Masking> & {
  site_id?: string | null;
  uid_root?: string | null;
  history: MaskingHistoryEntry[];
};

export interface MaskingHistoryEntry {
  new_status: string | null;
  when_changed: string;
  who_changed: string | null;
}

interface MaskingParams {
  LR: number | null;
  PA: number | null;
  IS: number | null;
  width: number | null;
  height: number | null;
  depth: number | null;
  fill: number | null;
  noise: number | null;
  form: string | null;
  function: string | null;
}

const maskingColumns = `
        image_equivalence_class_id,
        masking_parameters::text,
        masking_status,
        import_event_id,
        masking_exit_code`;

/** GET /v1/masking/visualreview/{visual_review_instance_id}/values */
export interface MaskingValueCounts {
  dicom_file_types: { dicom_file_type: string | null; count: number }[];
  masking_statuses: { masking_status: string | null; count: number }[];
}

export function registerMasking(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "not allowed");
  };
  app.prot("GET", "/v1/masking", notAllowed,
    doc({
      summary: "Get All Iecs",
      params: {
        args: { in: "query", required: true },
        kwargs: { in: "query", required: true },
      },
    }),
  );
  app.prot("GET", "/v1/masking/", notAllowed,
    doc({
      summary: "Get All Iecs",
      params: {
        args: { in: "query", required: true },
        kwargs: { in: "query", required: true },
      },
    }),
  );

  app.prot("GET", "/v1/masking/getwork", () => getWorkForMasker(app),
    doc({
      summary: "Get Work For Masker",
      description: "Get work for the worker program",
    }),
  );
  app.prot("POST", "/v1/masking/abortwork", (ctx) => abortMaskingWork(app, ctx),
    doc({
      summary: "Get Work For Masker",
      description: "Reset an IEC back to ready-to-process\n\nUsed only when Nopperabo is shutdown while working.\nIf the IEC is not in in-process status, nothing is done.",
      params: {
        iec: { in: "query", type: "integer", required: true },
      },
    }),
  );
  app.prot("GET", "/v1/masking/:iec", (ctx) => getMaskingDetails(app, ctx),
    doc<MaskingDetails>({
      summary: "Get Masking Details",
      description: "Return details about the given masking item, including history",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/masking/visualreview/:visual_review_instance_id/next-for-review",
    nextMaskingIEC(app, "process-complete"),
    doc({
      summary: "Get Next To Review For Review",
      description: "Return the \"next\" IEC in this VR that is waiting to be Reviewed\n\nThe IEC is chosen from the set of all IECs in this VR that are \nwaiting to be reviewed (masking_status of 'process-complete').\nIt then chooses one from this set randomly.\n\nThis can be used to select an IEC for a curator to work on. The \nexact one is chosen randomly as a cheap way to ensure multiple\npeople working on th same VR don't end up working on the same IEC.",
      params: {
        visual_review_instance_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/masking/visualreview/:visual_review_instance_id/next",
    nextMaskingIEC(app, "created"),
    doc({
      summary: "Get Next To Review",
      description: "Return the \"next\" IEC in this VR that is waiting to be Masked\n\nThe IEC is chosen from the set of all IECs in this VR that are \nflagged for Masking, minus those that are in a status that indicates\nthey have already had masking coordiantes assigned. It then chooses\none from this set randomly.\n\nThis can be used to select an IEC for a curator to work on. The \nexact one is chosen randomly as a cheap way to ensure multiple\npeople working on th same VR don't end up working on the same IEC.",
      params: {
        visual_review_instance_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/masking/visualreview/:visual_review_instance_id",
    (ctx) => getMaskingForVR(app, ctx),
    doc<number[]>({
      summary: "Get For Visualreview",
      description: "Return list of all IECs in this VR that are flagged for Masking, and\nare waiting to be masked (or those that are awaiting review).\n\nIf awaiting_review is true, it only returns those which are currently\nawaiting review (that is, masking_status is 'process-complete').\n\nIf awaiting_review is false, it only returns those IECs which are\nwaiting to be masked, or are rejected (that is, masking_status is\n'created' or 'rejected').",
      params: {
        visual_review_instance_id: { type: "integer" },
        awaiting_review: { in: "query", type: "boolean" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/masking/visualreview/:visual_review_instance_id/values",
    (ctx) => getMaskingValues(app, ctx),
    doc<MaskingValueCounts>({
      summary: "Get Masking Values For Vr",
      description: "Get list of valid values for use in filtering, for the given VR.\n\nReturns the valid values for: masking_status and dicom_file_type,\nscoped to IECs in this VR that are flagged for masking.",
      params: {
        visual_review_instance_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "POST",
    "/v1/masking/visualreview/:visual_review_instance_id/filter",
    (ctx) => getMaskingFiltered(app, ctx),
    doc({
      summary: "Get Masking Filtered For Vr",
      description: "Return a filtered list of IECs flagged for masking in this VR. Use * for wildcard.\n\nResults are always in ascending order.",
      params: {
        visual_review_instance_id: { type: "integer" },
      },
      requestBody: {
        contentType: "application/json",
        fields: {
          dicom_file_type: {  },
          masking_status: {  },
        },
      },
    }),
  );

  app.prot("GET", "/v1/masking/:iec/reviewfiles", (ctx) =>
    getMaskingReviewFiles(app, ctx),
    doc({
      summary: "Get Iec Review Files",
      description: "Get list of completed files for review",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/masking/:iec/reviewfiles/download", (ctx) =>
    downloadMaskingReviewFiles(app, ctx),
    doc({
      summary: "Get Iec Files",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot("POST", "/v1/masking/:iec/mask", (ctx) => requestMasking(app, ctx),
    doc({
      summary: "Request For Masking",
      description: "Flag for masking\n\nCreates a new entry in `masking` for this IEC.",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot("POST", "/v1/masking/:iec/parameters", (ctx) =>
    updateMaskingParameters(app, ctx),
    doc({
      summary: "Update Masking Parameters",
      description: "Update/Set masking parameters",
      params: {
        iec: { type: "integer" },
      },
      requestBody: {
        contentType: "application/json",
        fields: {
          LR: { type: "integer", required: true },
          PA: { type: "integer", required: true },
          IS: { type: "integer", required: true },
          width: { type: "integer", required: true },
          height: { type: "integer", required: true },
          depth: { type: "integer", required: true },
          fill: { type: "integer" },
          noise: { type: "integer" },
          form: {  },
          function: {  },
        },
      },
    }),
  );
  app.prot("POST", "/v1/masking/:iec/complete", (ctx) =>
    markMaskingComplete(app, ctx),
    doc({
      summary: "Mark Processing Complete",
      description: "Mark as process-complete\n\nThis should not be called by users.\nThe new ID needs to be submitted in the body as json, as\n{ import_event_id: x, exit_code: 0 }",
      params: {
        iec: { type: "integer" },
      },
      requestBody: {
        contentType: "application/json",
        fields: {
          import_event_id: { type: "integer", required: true },
          exit_code: { type: "integer", required: true },
        },
      },
    }),
  );
  app.prot("POST", "/v1/masking/:iec/accept", setMaskingStatus(app, "accepted"),
    doc({
      summary: "Mark Accept",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot("POST", "/v1/masking/:iec/reject", setMaskingStatus(app, "rejected"),
    doc({
      summary: "Mark Reject",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot("POST", "/v1/masking/:iec/skip", setMaskingStatus(app, "skipped"),
    doc({
      summary: "Mark Accept",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
  app.prot(
    "POST",
    "/v1/masking/:iec/nonmaskable",
    setMaskingStatus(app, "nonmaskable"),
    doc({
      summary: "Mark Accept",
      params: {
        iec: { type: "integer" },
      },
    }),
  );
}

async function getWorkForMasker(app: App): Promise<Response> {
  const row = await app.db.fetchOne(
    `
    update masking
    set masking_status = 'in-process'
    where image_equivalence_class_id = (
        select image_equivalence_class_id
        from masking
        where masking_status = 'ready-to-process'
        limit 1
        for update skip locked
    )
    returning image_equivalence_class_id
    `,
  );
  if (!row) throw new HttpError(404, "Not Found");
  return jsonResponse(row);
}

async function abortMaskingWork(app: App, ctx: Ctx): Promise<Response> {
  const iec = queryInt(ctx, "iec", 0);
  if (!ctx.url.searchParams.has("iec")) {
    throw new HttpError(422, 'query parameter "iec" is required');
  }
  await app.db.exec(
    `
    update masking
    set masking_status = 'ready-to-process'
    where image_equivalence_class_id = $1
      and masking_status = 'in-process'
    `,
    [iec],
  );
  return jsonResponse(null);
}

async function requestMasking(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");

  let row;
  try {
    row = await app.db.fetchOne(
      `
      insert into masking
      (image_equivalence_class_id)
      values
      ($1)
      returning ${maskingColumns}
      `,
      [iec],
    );
  } catch (err) {
    if (isUniqueViolation(err)) throw new HttpError(409, "Already exists");
    if (isForeignKeyViolation(err)) {
      throw new HttpError(422, "Invalid IEC supplied");
    }
    throw err;
  }

  await insertMaskingHistory(app, iec, "created", ctx.user!.user_id);
  return jsonResponse(row ?? []);
}

async function insertMaskingHistory(
  app: App,
  iec: number,
  status: string,
  userId: number,
): Promise<void> {
  await app.db.exec(
    `
    insert into masking_history
    values
    ($1, $2, now(), $3)
    `,
    [iec, status, userId],
  );
}

async function getMaskingDetails(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");

  const row = await app.db.fetchOne(
    `
    with input_image as (
        select distinct image_equivalence_class_id, site_id
        from masking
        natural join image_equivalence_class_input_image
        natural join ctp_file
    ), uid_root as (
        select input_image.*, uid_root
        from input_image
        join submissions on submissions.site_code || submissions.collection_code = input_image.site_id
    )

    select
        image_equivalence_class_id,
        masking_parameters::text,
        masking_status,
        import_event_id,
        masking_exit_code,
        site_id,
        uid_root
    from masking
    natural left join uid_root
    where image_equivalence_class_id = $1
    `,
    [iec],
  );

  const history = await app.db.fetch(
    `
    select
        h.new_status,
        h.when_changed::text,
        u.user_name as who_changed
    from masking_history h
    join auth.users u on u.user_id = h.who_changed
    where image_equivalence_class_id = $1
    `,
    [iec],
    { when_changed: "tstz" },
  );

  // Missing rows still produce {"history": [...]}, matching
  // dict(fetch_one_result) on an empty result.
  const out = row ?? {};
  out.history = history;
  return jsonResponse(out);
}

async function updateMaskingParameters(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");
  const body = await decodeJsonBody<Partial<MaskingParams>>(ctx.req);

  for (const name of ["LR", "PA", "IS", "width", "height", "depth"] as const) {
    if (body[name] === undefined || body[name] === null) {
      throw new HttpError(422, `body field "${name}" is required`);
    }
  }

  // Serialized the same way pydantic's model_dump_json does, so the
  // stored parameters keep the same field order and null handling.
  const params: MaskingParams = {
    LR: body.LR!,
    PA: body.PA!,
    IS: body.IS!,
    width: body.width!,
    height: body.height!,
    depth: body.depth!,
    fill: body.fill ?? null,
    noise: body.noise ?? null,
    form: body.form ?? "cylinder",
    function: body.function ?? "mask",
  };
  const jsonStr = pyJson(params);

  const newStatus = "ready-to-process";
  try {
    await app.db.exec(
      `
      INSERT INTO masking (image_equivalence_class_id, masking_status, masking_parameters)
      VALUES ($1, $2, $3)
      ON CONFLICT (image_equivalence_class_id)
      DO UPDATE SET
          masking_status = EXCLUDED.masking_status,
          masking_parameters = EXCLUDED.masking_parameters
      `,
      [iec, newStatus, jsonStr],
    );
  } catch (err) {
    if (isForeignKeyViolation(err)) {
      throw new HttpError(422, "Invalid IEC supplied");
    }
    throw err;
  }

  await insertMaskingHistory(app, iec, newStatus, ctx.user!.user_id);

  // Echo the parameters back, like the Python version returns `item`.
  return jsonResponse(params);
}

async function markMaskingComplete(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");
  const body = await decodeJsonBody<{
    import_event_id?: number | null;
    exit_code?: number | null;
  }>(ctx.req);

  if (body.import_event_id == null || body.exit_code == null) {
    throw new HttpError(422, "import_event_id and exit_code are required");
  }

  let newStatus = "process-complete";
  let importEventId: number | null = body.import_event_id;
  if (body.exit_code !== 0) {
    newStatus = "errored";
    importEventId = null;
  }

  try {
    await app.db.exec(
      `
      update masking
      set import_event_id = $1,
          masking_exit_code = $2,
          masking_status = $3
      where image_equivalence_class_id = $4
      `,
      [importEventId, body.exit_code, newStatus, iec],
    );
  } catch (err) {
    if (isForeignKeyViolation(err)) {
      throw new HttpError(422, "Invalid IEC supplied");
    }
    throw err;
  }

  await insertMaskingHistory(app, iec, newStatus, ctx.user!.user_id);

  return jsonResponse({
    import_event_id: body.import_event_id,
    exit_code: body.exit_code,
  });
}

/**
 * Covers the accept/reject/skip/nonmaskable family: update the status,
 * record history, return null (the Python handlers have no return
 * value).
 */
function setMaskingStatus(app: App, newStatus: string): Handler {
  return async (ctx) => {
    const iec = pathInt(ctx, "iec");
    try {
      await app.db.exec(
        `
        update masking
        set masking_status = $1
        where image_equivalence_class_id = $2
        `,
        [newStatus, iec],
      );
    } catch (err) {
      if (isForeignKeyViolation(err)) {
        throw new HttpError(422, "Invalid IEC supplied");
      }
      throw err;
    }
    await insertMaskingHistory(app, iec, newStatus, ctx.user!.user_id);
    return jsonResponse(null);
  };
}

/**
 * Pick a random IEC in the VR with the given masking status (used to
 * hand out work to curators).
 */
function nextMaskingIEC(app: App, status: string): Handler {
  // The two Python queries differ only in the required status (and a
  // join to file_import in the review variant, which does not change
  // the picked id).
  const sql = `
    with all_ready_iecs as (
        select
            image_equivalence_class_id
        from
            image_equivalence_class
            natural join masking
        where
            visual_review_instance_id = $1
            and masking_status = $2
    )

    select *
    from all_ready_iecs
    order by random()
    limit 1
    `;
  const reviewSql = `
    with all_ready_for_review as (
        select
            image_equivalence_class_id
        from
            image_equivalence_class
            natural join masking
            natural join file_import
        where
            visual_review_instance_id = $1
            and masking_status = $2
    )

    select *
    from all_ready_for_review
    order by random()
    limit 1
    `;
  return async (ctx) => {
    const vr = pathInt(ctx, "visual_review_instance_id");
    const query = status === "process-complete" ? reviewSql : sql;
    const row = await app.db.fetchOne(query, [vr, status]);
    if (!row) throw errNoRecords();
    // Python returns record[0]: just the id.
    return jsonResponse(Object.values(row)[0]);
  };
}

async function getMaskingForVR(app: App, ctx: Ctx): Promise<Response> {
  const vr = pathInt(ctx, "visual_review_instance_id");
  if (queryBool(ctx, "awaiting_review", false)) {
    return fetchFirstColumn(
      app,
      `
      select
          image_equivalence_class_id
      from
          image_equivalence_class
          natural join masking
      where
          visual_review_instance_id = $1
          and masking_status = 'process-complete'
      `,
      [vr],
    );
  }
  return fetchFirstColumn(
    app,
    `
    select
        image_equivalence_class_id
    from
        image_equivalence_class
        natural join masking
    where
        visual_review_instance_id = $1
        and masking_status in ('created', 'rejected')
    `,
    [vr],
  );
}

async function getMaskingValues(app: App, ctx: Ctx): Promise<Response> {
  const vr = pathInt(ctx, "visual_review_instance_id");

  const dicomFileTypes = await app.db.fetch(
    `
    with iecs as (
        select image_equivalence_class_id
        from image_equivalence_class
        natural join masking
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

  const maskingStatuses = await app.db.fetch(
    `
    select
        masking_status,
        count(*) as count
    from
        image_equivalence_class
        natural join masking
    where
        visual_review_instance_id = $1
    group by 1
    `,
    [vr],
    { count: "int8" },
  );

  if (
    dicomFileTypes.length === 0 &&
    maskingStatuses.length === 0 &&
    !(await vrExists(app, vr))
  ) {
    throw new HttpError(404, "invalid visual review id");
  }

  return jsonResponse({
    dicom_file_types: dicomFileTypes,
    masking_statuses: maskingStatuses,
  });
}

async function getMaskingFiltered(app: App, ctx: Ctx): Promise<Response> {
  const vr = pathInt(ctx, "visual_review_instance_id");
  const body = await decodeJsonBody<Record<string, unknown>>(ctx.req);

  const query = {
    sql: `
    with iecs as (
        select
        image_equivalence_class_id,
        masking_status,
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
        natural join masking
        where visual_review_instance_id = $1
    )

    select image_equivalence_class_id
    from iecs
    where 1 = 1
    `,
  };
  const args: unknown[] = [vr];
  appendFilter(body, "dicom_file_type", "dicom_file_type", query, args);
  appendFilter(body, "masking_status", "masking_status", query, args);
  query.sql += "order by 1";

  const rows = await app.db.fetch(query.sql, args);
  if (rows.length === 0 && !(await vrExists(app, vr))) {
    throw new HttpError(404, "invalid visual review id");
  }
  return jsonResponse(firstColumn(rows));
}

async function getMaskingReviewFiles(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");
  const rows = await app.db.fetch(
    `
    select distinct
        file_id,
        file_storage_root_id || '/' || file_location.rel_path as path,
        image_type,
        coalesce(number_of_frames, 1) as frame_count,
        iop,
        ipp
    from
        masking
        natural join file_import
        natural join dicom_file
        left join file_location using (file_id)
        natural left join file_image
        natural left join image
        natural left join image_geometry
    where
        image_equivalence_class_id = $1
    `,
    [iec],
  );
  if (rows.length === 0) throw errNoRecords();

  const [sorted] = iecFrameList(rows);

  // The consistency guess is deliberately ignored (see the TODO in the
  // Python source): the UI expects volumetric=true.
  return jsonResponse({
    volumetric: true,
    frames: sorted.map((f) => ({
      file_id: f.fileId,
      path: f.path,
      num_of_frames: f.frameCount,
    })),
  });
}

async function downloadMaskingReviewFiles(app: App, ctx: Ctx): Promise<Response> {
  const iec = pathInt(ctx, "iec");
  const rows = await app.db.fetch<{ file: string | null }>(
    `
    select
        root_path || '/' || file_location.rel_path as file
    from
        masking
        natural join file_import
        join file_location using(file_id)
        natural join file_storage_root
    where
        image_equivalence_class_id = $1
    `,
    [iec],
  );
  return streamZip(
    rows.map((row) => row.file ?? ""),
    `${iec}.zip`,
  );
}
