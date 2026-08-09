// Helpers matching FastAPI's response conventions ({"detail": ...}
// error bodies, JSON responses, common error shapes).

import { pyJson } from "./pyjson";

/** Mirrors FastAPI's HTTPException. */
export class HttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
    public readonly headers?: Record<string, string>,
  ) {
    super(`http ${status}: ${String(detail)}`);
  }
}

/**
 * Reproduces an unhandled Python exception: Starlette's
 * ServerErrorMiddleware answers with a plain-text 500.
 */
export class InternalError extends Error {}

export function plainInternalError(): Response {
  return new Response("Internal Server Error", {
    status: 500,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

/** The common `HTTPException(404, "no records returned")`. */
export function errNoRecords(): HttpError {
  return new HttpError(404, "no records returned");
}

/** Serialize v with Python float conventions as an HTTP response. */
export function jsonResponse(v: unknown, status = 200): Response {
  return new Response(pyJson(v), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * A response whose body streams. The gzip middleware compresses these
 * unconditionally (Starlette's GZipMiddleware policy for streamed
 * responses) instead of buffering to check the 500-byte minimum.
 */
export class StreamResponse extends Response {}
