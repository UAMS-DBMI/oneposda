// Ports papi/routes/dump.py: an HTML-formatted DICOM dump produced by
// an external script.

import type { App, Ctx } from "../server";
import { pathInt } from "../server";
import { HttpError } from "../httpx";

interface FilePathRow {
  file: string | null;
}

export function registerDump(app: App): void {
  app.prot("GET", "/v1/dump/:file_id", (ctx) => dumpDicom(app, ctx));
}

async function dumpDicom(app: App, ctx: Ctx): Promise<Response> {
  const fileId = pathInt(ctx, "file_id");

  const row = await app.db.fetchOne<FilePathRow>(
    `
    select root_path || '/' || rel_path as file
    from
        file_location
        natural join file_storage_root
    where file_id = $1
    `,
    [fileId],
  );
  if (!row) {
    throw new HttpError(404, `file_id ${fileId} does not exist`);
  }

  const proc = Bun.spawn([app.cfg.dumpScript, row.file ?? ""], {
    stdout: "pipe",
    stderr: "ignore",
  });
  const out = new Uint8Array(await new Response(proc.stdout).arrayBuffer());
  if ((await proc.exited) !== 0) {
    throw new Error("dump script failed");
  }

  // The Python version decodes as utf-8 and falls back to a chardet
  // guess; here anything that isn't valid utf-8 is treated as latin-1,
  // which covers the DICOM text encodings seen in practice.
  let body: string;
  try {
    body = new TextDecoder("utf-8", { fatal: true }).decode(out);
  } catch {
    body = new TextDecoder("latin1").decode(out);
  }

  return new Response(body, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
