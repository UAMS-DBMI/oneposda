// Ports papi/routes/work.py.

import type { App, Ctx } from "../server";
import { doc, type OrEmpty } from "../openapi";
import { pathInt, pathStr, queryInt } from "../server";
import { HttpError } from "../httpx";
import { fetchFirstColumn, fetchOneJson } from "./common";

/** GET /v1/work/items/{work_id} — work.* plus subprocess columns. */
export interface WorkItem {
  work_id: number;
  node_hostname: string | null;
  subprocess_invocation_id: number | null;
  input_file_id: number | null;
  status: string | null;
  running: boolean;
  finished: boolean;
  failed: boolean;
  stdout_file_id: number | null;
  stderr_file_id: number | null;
  background_queue_name: string | null;
  metrics: string | null; // jsonb, returned as raw text
  background_subprocess_id: number | null;
  activity_id: number | null;
  invoking_user: string | null;
  since_invocation: number | null; // interval as total seconds
  command_line: string | null;
  when_invoked: string | null;
  user_to_notify: string | null;
}

export function registerWork(app: App): void {
  app.prot("GET", "/v1/work/items", (ctx) => getWorkItems(app, ctx),
    doc({
      summary: "Get Work Status",
      params: {
        status: { in: "query", required: true },
        count: { in: "query", type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/work/items/:work_id", (ctx) => getWorkItem(app, ctx),
    doc<OrEmpty<WorkItem>>({
      summary: "Get Work Status",
      params: {
        work_id: { type: "integer" },
      },
    }),
  );
  app.prot("GET", "/v1/work/queues/:queue_name", (ctx) => getWorkQueue(app, ctx),
    doc({
      summary: "Get Work Status",
      params: {
        count: { in: "query", type: "integer" },
      },
    }),
  );
}

async function getWorkItems(app: App, ctx: Ctx): Promise<Response> {
  if (!ctx.url.searchParams.has("status")) {
    throw new HttpError(422, 'query parameter "status" is required');
  }
  return fetchFirstColumn(
    app,
    `
    select
        work_id
    from
        work
    where
        status = $1
    limit $2
    `,
    [ctx.url.searchParams.get("status"), queryInt(ctx, "count", 20)],
  );
}

async function getWorkItem(app: App, ctx: Ctx): Promise<Response> {
  // The Python query selects work.* plus joined columns (including
  // node_hostname, a duplicate of the work.* column that collapses in
  // the response); expanded here with timestamps/intervals cast for
  // faithful serialization.
  return fetchOneJson(
    app,
    `
      select
            work.work_id,
            work.node_hostname,
            work.subprocess_invocation_id,
            work.input_file_id,
            work.status,
            work.running,
            work.finished,
            work.failed,
            work.stdout_file_id,
            work.stderr_file_id,
            work.background_queue_name,
            work.metrics::text,
            background_subprocess_id,
            activity_id,
            invoking_user,
            now() - when_invoked as since_invocation,
            command_line,
            when_invoked::text,
            user_to_notify
        from
            work
            left join subprocess_invocation using (subprocess_invocation_id)
            left join background_subprocess using (subprocess_invocation_id)
            left join activity_task_status using (subprocess_invocation_id)
        where work_id = $1
    `,
    [pathInt(ctx, "work_id")],
    { since_invocation: "interval", when_invoked: "tstz" },
  );
}

async function getWorkQueue(app: App, ctx: Ctx): Promise<Response> {
  return fetchFirstColumn(
    app,
    `
    select
        work_id
    from
        work
    where
        background_queue_name = $1
        and finished = false
        and running = false
        and failed = false
    order by work_id desc
    limit $2
    `,
    [pathStr(ctx, "queue_name"), queryInt(ctx, "count", 20)],
  );
}
