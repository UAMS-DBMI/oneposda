// Shared handler helpers, mirroring the Python idioms
// (Database.fetch/fetch_one rendered straight to JSON, FileResponse).

import { statSync } from "node:fs";
import type { Convs } from "../pgconvert";
import type { Row } from "../db";
import type { App } from "../server";
import { HttpError, jsonResponse, StreamResponse } from "../httpx";

/** Run a query and respond with all rows as a JSON array. */
export async function fetchJson(
  app: App,
  sql: string,
  params: unknown[] = [],
  convs?: Convs,
): Promise<Response> {
  return jsonResponse(await app.db.fetch(sql, params, convs));
}

/**
 * Respond with the first row as a JSON object. When the query matches
 * nothing this responds [] — the Python Database.fetch_one helper
 * returns an empty list in that case and FastAPI serializes it as-is.
 */
export async function fetchOneJson(
  app: App,
  sql: string,
  params: unknown[] = [],
  convs?: Convs,
): Promise<Response> {
  const row = await app.db.fetchOne(sql, params, convs);
  return jsonResponse(row ?? []);
}

/** The first column of every row (the `[x[0] for x in rows]` idiom). */
export function firstColumn(rows: Row[]): unknown[] {
  return rows.map((row) => Object.values(row)[0]);
}

/** Run a query and respond with the first column as a JSON array. */
export async function fetchFirstColumn(
  app: App,
  sql: string,
  params: unknown[] = [],
  convs?: Convs,
): Promise<Response> {
  return jsonResponse(firstColumn(await app.db.fetch(sql, params, convs)));
}

/**
 * Decode a JSON request body, returning a 422 (FastAPI's validation
 * status) when the body cannot be parsed. An empty body decodes as {}.
 */
export async function decodeJsonBody<T>(req: Request): Promise<T> {
  const body = await req.text();
  if (body.length === 0) return {} as T;
  try {
    return JSON.parse(body) as T;
  } catch (err) {
    throw new HttpError(422, `invalid JSON body: ${err}`);
  }
}

/** Starlette's FileResponse default media type policy. */
export function guessMediaType(path: string): string {
  const dot = path.lastIndexOf(".");
  const ext = dot >= 0 ? path.slice(dot).toLowerCase() : "";
  return mimeTypes[ext] ?? "text/plain; charset=utf-8";
}

const mimeTypes: Record<string, string> = {
  ".json": "application/json",
  ".txt": "text/plain; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".htm": "text/html; charset=utf-8",
  ".csv": "text/csv; charset=utf-8",
  ".xml": "text/xml; charset=utf-8",
  ".pdf": "application/pdf",
  ".zip": "application/zip",
  ".gz": "application/gzip",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".dcm": "application/dicom",
  ".nii": "application/octet-stream",
  ".mp4": "video/mp4",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
};

/**
 * Stream a file like Starlette's FileResponse, honoring single-range
 * requests. When downloadName is non-empty a Content-Disposition
 * attachment header is added.
 */
export function serveFile(
  req: Request,
  path: string,
  downloadName = "",
  extraHeaders: Record<string, string> = {},
): Response {
  let size: number;
  let mtime: Date;
  try {
    const st = statSync(path);
    if (!st.isFile()) throw new Error("not a file");
    size = st.size;
    mtime = st.mtime;
  } catch {
    throw new HttpError(404, "File not found on disk");
  }

  const headers = new Headers({
    "Content-Type": guessMediaType(path),
    "Accept-Ranges": "bytes",
    "Last-Modified": mtime.toUTCString(),
    ...extraHeaders,
  });
  if (downloadName !== "") {
    headers.set("Content-Disposition", `attachment; filename="${downloadName}"`);
  }

  const file = Bun.file(path);
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.get("Range") ?? "");
  if (range && (range[1] !== "" || range[2] !== "")) {
    let start: number;
    let end: number; // exclusive
    if (range[1] === "") {
      start = Math.max(0, size - Number(range[2]));
      end = size;
    } else {
      start = Number(range[1]);
      end = range[2] === "" ? size : Math.min(size, Number(range[2]) + 1);
    }
    if (start >= size || start >= end) {
      return new Response(null, {
        status: 416,
        headers: { "Content-Range": `bytes */${size}` },
      });
    }
    headers.set("Content-Range", `bytes ${start}-${end - 1}/${size}`);
    headers.set("Content-Length", String(end - start));
    return new StreamResponse(file.slice(start, end).stream(), {
      status: 206,
      headers,
    });
  }

  headers.set("Content-Length", String(size));
  return new StreamResponse(file.stream(), { headers });
}

/**
 * The contents of path starting at offset, mirroring the Python "seek
 * then read to EOF" pattern used for pixel data.
 */
export async function readFileFrom(
  path: string,
  offset: number,
): Promise<Uint8Array> {
  const buf = await Bun.file(path).arrayBuffer();
  return new Uint8Array(buf.slice(offset));
}
