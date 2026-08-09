// HTTP server assembly: route table, auth middleware, request
// parameter helpers matching FastAPI's validation errors, and the gzip
// policy of Starlette's GZipMiddleware (minimum_size=500, level 9).

import { createGzip } from "node:zlib";
import { Readable } from "node:stream";
import type { Config } from "./config";
import type { Db } from "./db";
import type { AuthService, User } from "./auth";
import type { RouteDoc } from "./openapi";
import {
  HttpError,
  InternalError,
  jsonResponse,
  plainInternalError,
  StreamResponse,
} from "./httpx";

// FastAPI's root_path="/papi": the nginx proxy forwards the full
// request path including this prefix and the app strips it. Requests
// without the prefix (direct access) work as well — every route is
// registered under both.
const ROOT_PATH = "/papi";

const GZIP_MIN_SIZE = 500;
const GZIP_LEVEL = 9;

export interface Ctx {
  req: Request;
  params: Record<string, string>;
  url: URL;
  /** The logged-in user. Set on protected routes; null on public ones. */
  user: User | null;
}

export type Handler = (ctx: Ctx) => Response | Promise<Response>;

type BunRouteHandler = (req: Request & { params?: unknown }) => Promise<Response>;

/** A registered route, kept so tests can assert documentation coverage.
 * The OpenAPI document itself is generated from the source, not from
 * this table — see src/openapi.ts. */
export interface RouteInfo {
  method: string;
  path: string;
  needAuth: boolean;
  doc: RouteDoc | undefined;
}

export class App {
  private routes = new Map<string, Record<string, BunRouteHandler>>();
  /** Every registration, in declaration order. */
  readonly registered: RouteInfo[] = [];

  constructor(
    public readonly cfg: Config,
    public readonly db: Db,
    public readonly auth: AuthService,
  ) {}

  /** Register a route that does not require login. */
  pub(method: string, path: string, h: Handler, d?: RouteDoc): void {
    this.add(method, path, h, false, d);
  }

  /** Register a route behind the login middleware. */
  prot(method: string, path: string, h: Handler, d?: RouteDoc): void {
    this.add(method, path, h, true, d);
  }

  private add(
    method: string,
    path: string,
    h: Handler,
    needAuth: boolean,
    d?: RouteDoc,
  ): void {
    this.registered.push({ method, path, needAuth, doc: d });
    const wrapped: BunRouteHandler = async (req) => {
      const ctx: Ctx = {
        req,
        params: (req.params ?? {}) as Record<string, string>,
        url: new URL(req.url),
        user: null,
      };
      let res: Response;
      try {
        if (needAuth) ctx.user = await this.auth.requireUser(req);
        res = await h(ctx);
      } catch (err) {
        res = errorResponse(err, method, path);
      }
      return withGzip(req, res);
    };
    for (const p of [path, ROOT_PATH + path]) {
      const entry = this.routes.get(p) ?? {};
      entry[method] = wrapped;
      this.routes.set(p, entry);
    }
  }

  /** The routes object for Bun.serve. */
  serveRoutes(): Record<string, Record<string, BunRouteHandler>> {
    return Object.fromEntries(this.routes);
  }
}

function errorResponse(err: unknown, method: string, path: string): Response {
  if (err instanceof HttpError) {
    const res = jsonResponse({ detail: err.detail }, err.status);
    for (const [k, v] of Object.entries(err.headers ?? {})) {
      res.headers.set(k, v);
    }
    return res;
  }
  if (!(err instanceof InternalError)) {
    console.error(`internal error on ${method} ${path}:`, err);
  }
  return plainInternalError();
}

/** FastAPI returns JSON bodies for 404s; match that for unknown paths. */
export function notFound(): Response {
  return jsonResponse({ detail: "Not Found" }, 404);
}

// --- request parameter helpers ---------------------------------------

export function pathStr(ctx: Ctx, name: string): string {
  return ctx.params[name] ?? "";
}

export function pathInt(ctx: Ctx, name: string): number {
  const raw = ctx.params[name] ?? "";
  if (!/^-?\d+$/.test(raw)) {
    throw new HttpError(422, `path parameter "${name}" must be an integer`);
  }
  return Number(raw);
}

/** A query parameter, or the fallback when absent. */
export function queryStr(ctx: Ctx, name: string, fallback: string): string {
  const v = ctx.url.searchParams.get(name);
  return v === null ? fallback : v;
}

export function queryStrPtr(ctx: Ctx, name: string): string | null {
  return ctx.url.searchParams.get(name);
}

/** An optional integer query parameter (null when absent), erroring
 * like FastAPI when the value isn't an integer. */
export function queryIntPtr(ctx: Ctx, name: string): number | null {
  const v = ctx.url.searchParams.get(name);
  if (v === null) return null;
  if (!/^-?\d+$/.test(v)) {
    throw new HttpError(422, `query parameter "${name}" must be an integer`);
  }
  return Number(v);
}

export function queryInt(ctx: Ctx, name: string, fallback: number): number {
  return queryIntPtr(ctx, name) ?? fallback;
}

export function queryBool(ctx: Ctx, name: string, fallback: boolean): boolean {
  const v = ctx.url.searchParams.get(name);
  if (v === null) return fallback;
  switch (v.toLowerCase()) {
    case "1":
    case "true":
    case "yes":
    case "on":
      return true;
    case "0":
    case "false":
    case "no":
    case "off":
      return false;
  }
  return fallback;
}

// --- gzip middleware --------------------------------------------------

function gzipBody(body: ReadableStream<Uint8Array>): ReadableStream<Uint8Array> {
  const gz = createGzip({ level: GZIP_LEVEL });
  const nodeStream = Readable.fromWeb(
    body as unknown as import("node:stream/web").ReadableStream,
  ).pipe(gz);
  return Readable.toWeb(nodeStream) as unknown as ReadableStream<Uint8Array>;
}

function gzipHeaders(headers: Headers): Headers {
  const h = new Headers(headers);
  h.set("Content-Encoding", "gzip");
  h.delete("Content-Length");
  h.append("Vary", "Accept-Encoding");
  return h;
}

/**
 * Compress a response for clients that accept it: buffered responses
 * only when they reach 500 bytes, streamed responses always — the same
 * policy as Starlette's GZipMiddleware.
 */
export async function withGzip(req: Request, res: Response): Promise<Response> {
  if (!(req.headers.get("Accept-Encoding") ?? "").includes("gzip")) return res;

  if (res instanceof StreamResponse) {
    if (!res.body) return res;
    return new Response(gzipBody(res.body), {
      status: res.status,
      headers: gzipHeaders(res.headers),
    });
  }

  const buf = new Uint8Array(await res.arrayBuffer());
  if (buf.byteLength < GZIP_MIN_SIZE) {
    return new Response(buf.byteLength === 0 ? null : buf, {
      status: res.status,
      headers: res.headers,
    });
  }
  return new Response(Bun.gzipSync(buf, { level: GZIP_LEVEL }), {
    status: res.status,
    headers: gzipHeaders(res.headers),
  });
}
