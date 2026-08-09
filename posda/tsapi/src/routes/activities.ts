// Ports papi/routes/activities.py.

import type { App, Ctx, Handler } from "../server";
import { doc } from "../openapi";
import { pathInt } from "../server";
import { InternalError, errNoRecords, jsonResponse } from "../httpx";
import type { Row } from "../db";
import { PyFloat } from "../pyjson";
import { fileOnDisk } from "./files";
import { serveFile } from "./common";

/** GET /v1/activities elements (response-model filtered). */
export interface ActivitySummary {
  activity_id: number;
  brief_description: string | null;
  who_created: string | null;
  when_created: string | null;
}

/** GET /v1/activities/{activity_id} elements. */
export interface TimelineEntry {
  timeline_id: number;
  operation_name: string | null;
  duration: string | null; // ISO 8601 (pydantic v2 style)
  activity_timepoint_id: number | null;
  file_count: number | null;
  user_name: string | null;
  command_line: string | null;
  when: string | null;
}

/** GET /v1/activities/{activity_id}/{timeline_id} */
export interface TimelineEntryDetail {
  command_line: string | null;
  start_time: string | null;
  end_time: string | null;
  operation_name: string | null;
  invoking_user: string | null;
  activity_timepoint_id: number | null;
  reports: { file_id: number; name: string }[];
}

/**
 * Mimics a FastAPI response_model: only the named columns survive, in
 * model order.
 */
function filterRowTo(row: Row, cols: string[]): Row {
  const out: Row = {};
  for (const c of cols) out[c] = row[c] ?? null;
  return out;
}

/**
 * Rewrite a UTC "+00:00" timestamp string into the "Z" form pydantic
 * v2 uses when serializing datetime model fields.
 */
export function pydanticDatetime(v: unknown): unknown {
  if (typeof v === "string" && v.endsWith("+00:00")) {
    return v.slice(0, -6) + "Z";
  }
  return v;
}

/**
 * Convert an interval (already reduced to total seconds by the db
 * layer) into pydantic v2's ISO 8601 form, e.g. "PT32.486489S",
 * "P1DT2H", "PT0S".
 */
export function pydanticDuration(v: unknown): unknown {
  if (!(v instanceof PyFloat)) return v;
  let us = Math.round(v.value * 1e6);
  let sign = "";
  if (us < 0) {
    sign = "-";
    us = -us;
  }

  const days = Math.floor(us / 86_400_000_000);
  us -= days * 86_400_000_000;
  const hours = Math.floor(us / 3_600_000_000);
  us -= hours * 3_600_000_000;
  const minutes = Math.floor(us / 60_000_000);
  us -= minutes * 60_000_000;
  const seconds = us / 1e6;

  let out = sign + "P";
  if (days > 0) out += `${days}D`;
  let timePart = "";
  if (hours > 0) timePart += `${hours}H`;
  if (minutes > 0) timePart += `${minutes}M`;
  if (seconds !== 0 || (days === 0 && timePart === "")) {
    timePart += `${seconds}S`;
  }
  if (timePart !== "") out += "T" + timePart;
  return out;
}

export function registerActivities(app: App): void {
  app.prot("GET", "/v1/activities", () => getAllActivities(app),
    doc<ActivitySummary[]>({
      summary: "Get All Activities",
      description: "Return a list of all active Activities in the system.",
    }),
  );
  app.prot("GET", "/v1/activities/", () => getAllActivities(app),
    doc<ActivitySummary[]>({
      summary: "Get All Activities",
      description: "Return a list of all active Activities in the system.",
    }),
  );

  app.prot("GET", "/v1/activities/:activity_id", (ctx) =>
    getActivity(app, ctx),
    doc<TimelineEntry[]>({
      summary: "Get Activity",
      description: "Return a list of Timeline Entries for the given activity.\n\nNOTE: timeline_id == subprocess_invocation_id",
      params: {
        activity_id: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/activities/:activity_id/:timeline_id", (ctx) =>
    getTimelineEntry(app, ctx),
    doc<TimelineEntryDetail>({
      summary: "Get Timeline Entry",
      description: "Return details about a single Timeline Entry.",
      params: {
        activity_id: { type: "integer" },
        timeline_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/activities/:activity_id/:timeline_id/input",
    timelineEntryFile(app, "input_file_id"),
    doc({
      summary: "Get Timeline Entry Input",
      description: "Return the raw input that was given to this subprocess. Usually this\nis a spreadsheet, or at least looks like one.",
      params: {
        activity_id: { type: "integer" },
        timeline_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/activities/:activity_id/:timeline_id/output",
    timelineEntryFile(app, "stdout_file_id"),
    doc({
      summary: "Get Timeline Entry Output",
      description: "Return the raw output (stdout) that this subprocess produced.",
      params: {
        activity_id: { type: "integer" },
        timeline_id: { type: "integer" },
      },
    }),
  );
  app.prot(
    "GET",
    "/v1/activities/:activity_id/:timeline_id/errors",
    timelineEntryFile(app, "stderr_file_id"),
    doc({
      summary: "Get Timeline Entry Errors",
      description: "Return the raw errors (stderr) that this subprocess produced.",
      params: {
        activity_id: { type: "integer" },
        timeline_id: { type: "integer" },
      },
    }),
  );
}

async function getAllActivities(app: App): Promise<Response> {
  // The Python query is `select * from activity`; only the
  // response-model columns survive serialization, so select just those.
  const rows = await app.db.fetch(
    `
    select
        activity_id,
        brief_description,
        who_created,
        when_created::text
    from activity
    where when_closed is null
    `,
    [],
    { when_created: "tstz" },
  );

  return jsonResponse(
    rows.map((row) => ({
      ...filterRowTo(row, [
        "activity_id",
        "brief_description",
        "who_created",
        "when_created",
      ]),
      when_created: pydanticDatetime(row.when_created),
    })),
  );
}

async function getActivity(app: App, ctx: Ctx): Promise<Response> {
  // As above, the outer `select *` is reduced to the response-model
  // columns.
  const rows = await app.db.fetch(
    `
    with timepoints as (
        select
            activity_id,
            a.when_created as activity_created,
            brief_description as activity_description,
            activity_timepoint_id,
            t.when_created as timepoint_created,
            comment,
            creating_user,
            (
                select count(file_id)
                from activity_timepoint_file atf
                where atf.activity_timepoint_id = t.activity_timepoint_id
            ) as file_count
        from
            activity a
            join activity_timepoint t using (activity_id)
        where
            activity_id = $1
        order by
            t.when_created desc

    ), inbox_content as (
    select
        user_name,
        user_inbox_content_id as timeline_id,
        operation_name,
        when_script_started as when,
        when_script_ended as ended,
        when_script_ended - when_script_started as duration,
        file_id,
        subprocess_invocation_id as sub_id,
        command_line,
        file_id_in_posda as spreadsheet_file_id

        from activity_inbox_content
        natural join user_inbox
        natural join user_inbox_content
        natural join background_subprocess_report
        natural join background_subprocess
        natural join subprocess_invocation
        natural left join spreadsheet_uploaded
    where
        activity_id = $1
    order by
        when_script_started desc
    )

    select
        timeline_id,
        operation_name,
        duration,
        activity_timepoint_id,
        file_count,
        user_name,
        command_line,
        inbox_content.when::text
    from inbox_content
    left join timepoints
        on timepoints.timepoint_created
            between inbox_content.when and inbox_content.ended
    `,
    [pathInt(ctx, "activity_id")],
    { duration: "interval", file_count: "int8", when: "tstz" },
  );

  return jsonResponse(
    rows.map((row) => ({
      ...filterRowTo(row, [
        "timeline_id",
        "operation_name",
        "duration",
        "activity_timepoint_id",
        "file_count",
        "user_name",
        "command_line",
        "when",
      ]),
      duration: pydanticDuration(row.duration),
      when: pydanticDatetime(row.when),
    })),
  );
}

async function getTimelineEntry(app: App, ctx: Ctx): Promise<Response> {
  const timelineId = pathInt(ctx, "timeline_id");

  const reportRows = await app.db.fetch(
    `
    select
        file_id, name
    from
            background_subprocess_report
    where background_subprocess_id = (
            select background_subprocess_id
            from background_subprocess
            where subprocess_invocation_id = $1
    )
    `,
    [timelineId],
  );

  // The Python query is a `select *` over the whole join; only the
  // response-model columns survive.
  const row = await app.db.fetchOne(
    `
    select
        command_line,
        start_time::text,
        end_time::text,
        operation_name,
        invoking_user,
        activity_timepoint_id
    from
        subprocess_invocation
        natural join background_subprocess
        join activity_task_status using (subprocess_invocation_id)
        left join activity_timepoint
            on activity_timepoint.activity_id = activity_task_status.activity_id
            and activity_timepoint.when_created
                between background_subprocess.when_script_started
                and background_subprocess.when_script_ended
    where
        background_subprocess.subprocess_invocation_id = $1
    `,
    [timelineId],
    { start_time: "ts", end_time: "ts" },
  );
  if (!row) {
    // Python fails constructing the response model -> 500.
    throw new InternalError();
  }

  return jsonResponse({
    ...filterRowTo(row, [
      "command_line",
      "start_time",
      "end_time",
      "operation_name",
      "invoking_user",
      "activity_timepoint_id",
    ]),
    reports: reportRows,
  });
}

/**
 * Serve the input/stdout/stderr file recorded in the work table for a
 * subprocess.
 */
function timelineEntryFile(app: App, column: string): Handler {
  return async (ctx) => {
    const timelineId = pathInt(ctx, "timeline_id");
    const row = await app.db.fetchOne(
      `
      select ${column}
      from work
      where subprocess_invocation_id = $1
      `,
      [timelineId],
    );
    if (!row) throw errNoRecords();
    const fileId = Number(row[column] ?? 0);
    const path = await fileOnDisk(app, fileId);
    return serveFile(ctx.req, path, "", { "P-file_id": String(fileId) });
  };
}
