// Ports papi/routes/download.py. The router is mounted both under
// /v1/download and at the application root (the latter for backward
// compatibility), with no login requirement — access control is the
// security_hash in the URL.

import type { App, Ctx } from "../server";
import { pathInt, pathStr, queryBool } from "../server";
import { errNoRecords } from "../httpx";
import { serveFile } from "./common";
import { streamTarGz } from "../archive";

interface DownloadableFile {
  file: string | null;
  size: number | null;
  mime_type: string | null;
  report_name: string | null;
}

interface DownloadableDir {
  path: string | null;
}

/** Python's mimetypes.guess_extension for the stored mime types. */
function guessExtension(mimeType: string): string {
  switch (mimeType) {
    case "text/plain":
      return ".txt";
    case "text/csv":
      return ".csv";
    case "text/html":
      return ".html";
    case "application/json":
      return ".json";
    case "application/pdf":
      return ".pdf";
    case "application/zip":
      return ".zip";
    case "application/gzip":
      return ".gz";
  }
  return "";
}

export function registerDownload(app: App): void {
  for (const prefix of ["", "/v1/download"]) {
    app.pub("GET", `${prefix}/file/:downloadable_file_id/:hash`, (ctx) =>
      downloadFile(app, ctx),
    );
    app.pub("GET", `${prefix}/dir/:downloadable_dir_id/:hash`, (ctx) =>
      downloadDir(app, ctx),
    );
  }
}

async function downloadFile(app: App, ctx: Ctx): Promise<Response> {
  const id = pathInt(ctx, "downloadable_file_id");

  const row = await app.db.fetchOne<DownloadableFile>(
    `
    select
        root_path || '/' || rel_path as file,
        size,
        mime_type,
        name as report_name
    from downloadable_file
    natural join file
    natural join file_location
    natural join file_storage_root
    natural left join background_subprocess_report
    where downloadable_file_id = $1
      and security_hash = $2
      and (valid_until is null or now() < valid_until)
    `,
    [id, pathStr(ctx, "hash")],
  );
  if (!row) throw errNoRecords();

  const path = row.file ?? "";
  const mimeType = row.mime_type ?? "";
  const ext = guessExtension(mimeType);

  if (queryBool(ctx, "process", false)) {
    const cmd =
      row.report_name === "DciodvfySeriesReport"
        ? `/home/posda/posdatools/dciodvfymacro/run.sh ${path}`
        : `/home/posda/posdatools/phimacro/run.sh ${path}`;

    // Matches asyncio.create_subprocess_shell: the command line is
    // interpreted by the shell, stdout and stderr are concatenated.
    const proc = Bun.spawn(["/bin/sh", "-c", cmd], {
      stdout: "pipe",
      stderr: "pipe",
    });
    const [stdout, stderr] = await Promise.all([
      new Response(proc.stdout).arrayBuffer(),
      new Response(proc.stderr).arrayBuffer(),
    ]);
    await proc.exited;

    const body = new Uint8Array(stdout.byteLength + stderr.byteLength);
    body.set(new Uint8Array(stdout), 0);
    body.set(new Uint8Array(stderr), stdout.byteLength);
    return new Response(body, {
      headers: {
        "Content-Type": mimeType,
        "Content-Disposition": `attachment; filename="downloaded_file_${id}_macro${ext}"`,
      },
    });
  }

  return serveFile(ctx.req, path, `downloaded_file_${id}${ext}`);
}

async function downloadDir(app: App, ctx: Ctx): Promise<Response> {
  const id = pathInt(ctx, "downloadable_dir_id");

  const row = await app.db.fetchOne<DownloadableDir>(
    `
    select
        path
    from downloadable_dir
    where downloadable_dir_id = $1
      and security_hash = $2
    `,
    [id, pathStr(ctx, "hash")],
  );
  if (!row) throw errNoRecords();

  return streamTarGz(row.path ?? "", `downloaded_dir_${id}.tar.gz`);
}
