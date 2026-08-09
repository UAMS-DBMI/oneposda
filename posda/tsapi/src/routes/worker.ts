// Ports papi/routes/worker.py.

import type { App, Ctx } from "../server";
import { pathInt } from "../server";
import { pyJson } from "../pyjson";
import { decodeJsonBody, fetchOneJson } from "./common";

/** GET /v1/worker/status/{work_id} */
export interface WorkStatus {
  work_id: number;
  node_hostname: string | null;
  subprocess_invocation_id: number | null;
  input_file_id: number | null;
  status: string | null;
  running: boolean;
  finished: boolean;
  failed: boolean;
  stderr_file_id: number | null;
  stdout_file_id: number | null;
}

/** GET /v1/worker/subprocess/{subprocess_invocation_id} */
export interface SubprocessInfo {
  subprocess_invocation_id: number;
  command_line: string | null;
}

export function registerWorker(app: App): void {
  app.prot("GET", "/v1/worker/status/:work_id", (ctx) =>
    fetchOneJson(
      app,
      `
      select
          work_id,
          node_hostname,
          subprocess_invocation_id,
          input_file_id,
          status,
          running,
          finished,
          failed,
          stderr_file_id,
          stdout_file_id
      from
          work
      where
          work_id = $1
      `,
      [pathInt(ctx, "work_id")],
    ),
  );

  app.prot("POST", "/v1/worker/status/:work_id/running", (ctx) =>
    setWorkRunning(app, ctx),
  );

  app.prot("POST", "/v1/worker/status/:work_id/finished", (ctx) =>
    setWorkDone(
      app,
      ctx,
      `
      update
          work
      set
          running = false,
          finished = true,
          status = 'finished',
          stderr_file_id = $2,
          stdout_file_id = $3,
          metrics = $4
      where
          work_id = $1
      `,
    ),
  );

  app.prot("POST", "/v1/worker/status/:work_id/errored", (ctx) =>
    setWorkDone(
      app,
      ctx,
      `
      update
          work
      set
          running = false,
          failed = true,
          status = 'errored',
          stderr_file_id = $2,
          stdout_file_id = $3,
          metrics = $4
      where
          work_id = $1
      `,
    ),
  );

  app.prot("GET", "/v1/worker/subprocess/:subprocess_invocation_id", (ctx) =>
    fetchOneJson(
      app,
      `
      select
          subprocess_invocation_id,
          command_line
      from
          subprocess_invocation
      where
          subprocess_invocation_id = $1
      `,
      [pathInt(ctx, "subprocess_invocation_id")],
    ),
  );
}

async function setWorkRunning(app: App, ctx: Ctx): Promise<Response> {
  const workId = pathInt(ctx, "work_id");
  const details = await decodeJsonBody<{ node_hostname?: string | null }>(
    ctx.req,
  );
  // The Python version fetches an UPDATE without RETURNING, which
  // yields an empty list response.
  return fetchOneJson(
    app,
    `
    update
        work
    set
        running = true,
        status = 'running',
        node_hostname = $1
    where
        work_id = $2
    `,
    [details.node_hostname ?? null, workId],
  );
}

// The shared finished/errored update: the two tracked file ids are
// pulled out of the JSON body, and everything else is stored in the
// metrics column.
async function setWorkDone(
  app: App,
  ctx: Ctx,
  sql: string,
): Promise<Response> {
  const workId = pathInt(ctx, "work_id");
  const body = await decodeJsonBody<Record<string, unknown>>(ctx.req);

  const stderrFileId = body.stderr_file_id ?? null;
  const stdoutFileId = body.stdout_file_id ?? null;
  delete body.stderr_file_id;
  delete body.stdout_file_id;

  return fetchOneJson(app, sql, [
    workId,
    stderrFileId,
    stdoutFileId,
    pyJson(body),
  ]);
}
