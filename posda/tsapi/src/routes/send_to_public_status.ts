// Ports papi/routes/send_to_public_status.py.

import type { App, Ctx } from "../server";
import { doc } from "../openapi";
import { pathInt, pathStr, queryBool } from "../server";
import { HttpError, jsonResponse } from "../httpx";
import type { Row } from "../db";
import { curlCommand, parse, truncate } from "../evilparse";
import { fetchJson } from "./common";

/** GET /v1/send_to_public_status/report/{id} */
export interface PublicCopyReport {
  overal_status: { success: boolean | null; count: number }[];
  total_files: number;
  first_5_errors: PublicCopyError[];
}

export interface PublicCopyError {
  subprocess_invocation_id: string;
  file_id: string;
  collection: string;
  site: string;
  site_id: string;
  batch: string;
  filename: string;
  third_party_analysis_url: string | null;
  error_message: string;
  curl: string;
}

export function registerSendToPublicStatus(app: App): void {
  const notAllowed = () => {
    throw new HttpError(401, "test error, not allowed");
  };
  app.prot("GET", "/v1/send_to_public_status", notAllowed,
    doc({
      summary: "Get All Studies",
    }),
  );
  app.prot("GET", "/v1/send_to_public_status/", notAllowed,
    doc({
      summary: "Get All Studies",
    }),
  );

  app.prot(
    "GET",
    "/v1/send_to_public_status/report/:subprocess_invocation_id",
    (ctx) => publicCopyReport(app, ctx),
    doc({
      summary: "Report",
      params: {
        subprocess_invocation_id: { type: "integer" },
        pretty: { in: "query", type: "boolean" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/send_to_public_status/find_send_ready_to_begin_status_updates",
    () =>
      fetchJson(
        app,
        `
        select distinct
                subprocess_invocation_id
        from
                activity_task_status
                natural join public_copy_status
        where
                manual_update = true
        `,
      ),
    doc({
      summary: "Find Send Ready To Begin Status Updates",
    }),
  );

  app.prot(
    "GET",
    "/v1/send_to_public_status/get_success_percentage_for_send/:subprocess_invocation_id",
    (ctx) =>
      fetchJson(
        app,
        `
        select
            ('' || success::text || ' ' || ((count(*)/(select  sum(c) as t from
            ( select
                count(file_id) as c
                from
                    activity_timepoint_file
                where
                    activity_timepoint_id = (
                    select max(activity_timepoint_id)
                    from activity_timepoint
                    where activity_id = (
                        select activity_id
                        from activity_task_status
                        where subprocess_invocation_id = $1 )))
                        as sum_table)::float) * 100.0)::int || '%')::text as summary
        from
            public_copy_status
        where
            subprocess_invocation_id = $1
        group by
            success
        `,
        [pathInt(ctx, "subprocess_invocation_id")],
      ),
    doc({
      summary: "Get Success Percentage For Send",
      params: {
        subprocess_invocation_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/send_to_public_status/update_activity_status/:subprocess_invocation_id/:new_status",
    (ctx) =>
      fetchJson(
        app,
        `
        update
            activity_task_status
        set
            status_text = $2
        where
            activity_task_status.manual_update = true
            and subprocess_invocation_id = $1
        `,
        [
          pathInt(ctx, "subprocess_invocation_id"),
          pathStr(ctx, "new_status"),
        ],
      ),
    doc({
      summary: "Update Activity Status",
      params: {
        subprocess_invocation_id: { type: "integer" },
      },
    }),
  );

  app.prot(
    "GET",
    "/v1/send_to_public_status/finish_activity_status/:subprocess_invocation_id",
    (ctx) =>
      fetchJson(
        app,
        `
        update
            activity_task_status
        set
            manual_update = false
        where
            activity_task_status.manual_update = true
            and subprocess_invocation_id = $1
        `,
        [pathInt(ctx, "subprocess_invocation_id")],
      ),
    doc({
      summary: "Finish Activity Status",
      params: {
        subprocess_invocation_id: { type: "integer" },
      },
    }),
  );
}

async function publicCopyReport(app: App, ctx: Ctx): Promise<Response> {
  const id = pathInt(ctx, "subprocess_invocation_id");

  const rows = await app.db.fetch(
    `
    select
        success, count(file_id)
    from public_copy_status
    where subprocess_invocation_id = $1
    group by success
    `,
    [id],
    { count: "int8" },
  );

  let totalFiles = 0;
  for (const row of rows) totalFiles += Number(row.count ?? 0);

  const errRows = await app.db.fetch<{ error_message: string | null }>(
    `
    select
        error_message
    from public_copy_status
    where subprocess_invocation_id = $1
      and success = false
      limit 5
    `,
    [id],
  );

  const files: Row[] = errRows.map((errRow) => {
    // parse() throws on malformed messages, like the Python eval()
    // blowing up the whole request.
    const [file, firstError] = parse(errRow.error_message ?? "");
    return {
      subprocess_invocation_id: file.subprocessInvocationId,
      file_id: file.fileId,
      collection: file.collection,
      site: file.site,
      site_id: file.siteId,
      batch: file.batch,
      filename: file.filename,
      third_party_analysis_url: file.thirdPartyAnalysisUrl,
      error_message: truncate(firstError, 500),
      curl: curlCommand(file),
    };
  });

  if (queryBool(ctx, "pretty", false)) {
    return renderPrettyReport(id, rows, totalFiles, files);
  }

  return jsonResponse({
    overal_status: rows,
    total_files: totalFiles,
    first_5_errors: files,
  });
}

/** HTML-escape matching Go's html/template (the previous port). */
function esc(v: unknown): string {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&#34;")
    .replaceAll("'", "&#39;");
}

function renderPrettyReport(
  invocId: number,
  rows: Row[],
  totalFiles: number,
  files: Row[],
): Response {
  const statusRows = rows
    .map(
      (row) => `
<tr>
    <td>${esc(row.count)}</td>
    <td>${esc(row.success)}</td>
</tr>
`,
    )
    .join("");

  const fileTables = files
    .map(
      (f) => `
<table>
<tr>
    <th>file_id</th>
    <td><a href="/viewer/file/${esc(f.file_id)}" target="_blank">${esc(f.file_id)}</a></td>
</tr>
<tr>
    <th>collection</th>
    <td>${esc(f.collection)}</td>
</tr>
<tr>
    <th>site</th>
    <td>${esc(f.site)}</td>
</tr>
<tr>
    <th>site_id</th>
    <td>${esc(f.site_id)}</td>
</tr>
<tr>
    <th>filename</th>
    <td>${esc(f.filename)}</td>
</tr>
<tr>
    <th>batch</th>
    <td>${esc(f.batch)}</td>
</tr>
<tr>
    <th>third_party_analysis_url</th>
    <td>${esc(f.third_party_analysis_url)}</td>
</tr>
<tr>
    <th>error_message</th>
    <td>${esc(f.error_message)}</td>
</tr>
<tr>
    <th>API Command for NBIA Debugging</th>
    <td>
        ${esc(f.curl)}
    </td>
</tr>
</table>
`,
    )
    .join("");

  const html = `
<html>
<head>
    <title>Report for ${invocId}</title>
    <style type="text/css">
        body {
            background-color: #EEEEEE;
        }
        td, th {
            border: 2px solid #C7C7C7;
            padding: 10px;
        }
        th {
            text-align: right;
        }
        table {
            margin-bottom: 1em;
            border-collapse: collapse;
        }
    </style>
</head>
<body>
<h1>Public Copy Report for ID#${invocId}</h1>

<h3>Overall status</h3>
<table>
<tr>
    <th>Count of files</th>
    <th>Sucessful?</th>
</tr>
${statusRows}
<tr>
    <td>${totalFiles}</td>
    <td>Both</td>
</tr>
</table>

<h3>First 5 files that failed</h3>
${fileTables}

</body>
</html>
    `;

  return new Response(html, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
