// Ports papi/routes/dashboard.py: read-only monitoring queries.

import type { App } from "../server";
import { pathInt } from "../server";
import { HttpError } from "../httpx";
import { fetchJson } from "./common";

/** GET /v1/dashboard/slow_dbif_queries/{days} — query_invoked_by_dbif.* */
export interface SlowDbifQuery {
  query_invoked_by_dbif_id: number;
  query_name: string | null;
  invoking_user: string | null;
  query_start_time: string | null;
  query_end_time: string | null;
  number_of_rows: number | null;
  query_time: string | null;
}

/** GET /v1/dashboard/prbs */
export interface ProcessRunningInBackground {
  subprocess_invocation_id: number;
  background_subprocess_id: number;
  when_script_started: string | null;
  when_background_entered: string | null;
  command_line: string | null;
  time_in_background: string | null;
  background_pid: number | null;
}

/** GET /v1/dashboard/bsbu */
export interface BackgroundSubprocessByUser {
  invoking_user: string | null;
  count_background: number;
  avg_time_in_background: string | null;
}

/** GET /v1/dashboard/fwt and /v1/dashboard/fwl */
export interface FileWithoutType {
  file_id: number;
  digest: string | null;
  size: number | null;
  is_dicom_file: boolean | null;
  file_type: string | null;
  processing_priority: number | null;
  ready_to_process: boolean | null;
}

/** GET /v1/dashboard/tla */
export interface TableLockActivity {
  pid: number | null;
  usename: string | null;
  blocked_by: number[] | null;
  blocked_query: string | null;
}

/** GET /v1/dashboard/qrvi */
export interface QueryInvocationSummary {
  query_name: string | null;
  last_invocation: string | null;
  num_invocations: number;
  total_query_time: string | null;
  avg_query_time: number | null;
}

export function registerDashboard(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "test error, not allowed");
  };
  app.prot("GET", "/v1/dashboard", notAllowed);
  app.prot("GET", "/v1/dashboard/", notAllowed);

  app.prot("GET", "/v1/dashboard/slow_dbif_queries/:days", (ctx) =>
    fetchJson(
      app,
      `
      select
          query_invoked_by_dbif_id,
          query_name,
          invoking_user,
          query_start_time::text,
          query_end_time::text,
          number_of_rows,
          (query_end_time - query_start_time)::text as query_time
      from
          query_invoked_by_dbif
      where
          query_end_time is not null
          and (
          ( extract( day from(current_timestamp - query_end_time))::int < $1 )
          or ( extract( day from(current_timestamp - query_start_time))::int < $1 )
          )
      order by query_time desc
      limit 20;
      `,
      [pathInt(ctx, "days")],
      { query_start_time: "tstz", query_end_time: "tstz" },
    ),
  );

  app.prot("GET", "/v1/dashboard/prbs", () =>
    fetchJson(
      app,
      `
      select
        subprocess_invocation_id, background_subprocess_id,
        when_script_started::text, when_background_entered::text, command_line,
        (now()-when_background_entered)::text as time_in_background,
        background_pid
      from
        subprocess_invocation natural join background_subprocess
      where
        when_background_entered is not null and when_script_ended is null and
        subprocess_invocation_id != 0 and crash is null
      order by subprocess_invocation_id
      limit 20;
      `,
      [],
      { when_script_started: "tstz", when_background_entered: "tstz" },
    ),
  );

  app.prot("GET", "/v1/dashboard/bsbu", () =>
    fetchJson(
      app,
      `
      select
       invoking_user
       ,count(subprocess_invocation_id) as count_background
       ,avg(when_script_ended-when_background_entered)::text as avg_time_in_background
      from
        subprocess_invocation natural join background_subprocess
      where
        when_background_entered is not null
        and subprocess_invocation_id != 0
        and crash is null
        and extract(day from(now()- when_background_entered))::int < 7
      group by invoking_user;
      `,
      [],
      { count_background: "int8" },
    ),
  );

  app.prot("GET", "/v1/dashboard/fwt", () =>
    fetchJson(
      app,
      `
      select
          file_id, digest, size, is_dicom_file, file_type,
          processing_priority, ready_to_process
      from files_without_type
      limit 20;
      `,
    ),
  );

  app.prot("GET", "/v1/dashboard/fwl", () =>
    fetchJson(
      app,
      `
      select
          file_id, digest, size, is_dicom_file, file_type,
          processing_priority, ready_to_process
      from files_without_location
      limit 20;
      `,
    ),
  );

  // The file_imports_over_time view does not exist in current
  // databases, so this endpoint answers 500 in every implementation.
  app.prot("GET", "/v1/dashboard/ftc", () =>
    fetchJson(
      app,
      `
      select
          *
      from
          file_imports_over_time
      where
          importyear is not null
      order by
          importyear
          ,importmonth;
      `,
    ),
  );

  app.prot("GET", "/v1/dashboard/tla", () =>
    fetchJson(
      app,
      `
      select pid,
        usename,
        pg_blocking_pids(pid) as blocked_by,
        query as blocked_query
      from pg_stat_activity
      where cardinality(pg_blocking_pids(pid)) > 0;
      `,
    ),
  );

  app.prot("GET", "/v1/dashboard/qrvi", () =>
    fetchJson(
      app,
      `
      select
        query_name,
        max(query_start_time)::text  as last_invocation,
        count(query_invoked_by_dbif_id) as num_invocations,
        sum(query_end_time - query_start_time)::text  as total_query_time,
        extract(epoch from avg(query_end_time - query_start_time)) as avg_query_time
      from
        query_invoked_by_dbif
      where extract(day from query_start_time)::int < 31
      group by query_name
      order by avg_query_time  desc
      limit 120;
      `,
      [],
      { num_invocations: "int8", avg_query_time: "num" },
    ),
  );
}
