// Documentation metadata for route registrations.
//
// This is purely declarative: `doc()` returns its argument unchanged and
// the server never reads it at runtime. The OpenAPI document is produced
// at build time by scripts/genopenapi.ts, which walks the `app.pub(...)`
// and `app.prot(...)` calls in src/routes/ with the TypeScript compiler
// API and resolves the response type argument of `doc<T>()` into JSON
// Schema. Keeping the metadata in the source — next to the SQL and the
// row interface it describes — is what stops the spec from rotting.

/** A path or query parameter. `in` is inferred from the route path when
 * omitted: names appearing as `:name` segments are path parameters. */
export interface ParamDoc {
  in?: "path" | "query";
  type?: "string" | "integer" | "number" | "boolean";
  /** Path parameters are always required; query parameters default to
   * optional. */
  required?: boolean;
  description?: string;
  /** Rendered as the OpenAPI `example` value. */
  example?: string | number | boolean;
}

export interface BodyDoc {
  /** Defaults to application/json. */
  contentType?: string;
  description?: string;
  required?: boolean;
  /** Named fields, for form and JSON bodies described inline. */
  fields?: Record<string, ParamDoc>;
}

export interface RouteDoc {
  summary?: string;
  description?: string;
  /** Groups the operation in the UI. Defaults to the tag derived from
   * the first path segment after /v1. */
  tags?: string[];
  params?: Record<string, ParamDoc>;
  requestBody?: BodyDoc;
  /** Media type of a successful response when it is not JSON — set for
   * the endpoints that stream files, zips and pixel data. */
  produces?: string;
  /** Documented failure responses, as status -> description. The 401 of
   * protected routes and the 422 of routes with typed parameters are
   * added automatically. */
  errors?: Record<number, string>;
  /** Keep the route out of the published document (deprecated or
   * internal endpoints that still have to exist). */
  hidden?: boolean;
  /** Marks the operation deprecated in the UI. */
  deprecated?: boolean;
}

/**
 * A single-row response that degenerates to `[]` when the query matches
 * nothing.
 *
 * `fetchOneJson` returns the empty *list* rather than an object or a 404
 * when there are no rows — a quirk of the Python implementation that
 * both ports preserve. Endpoints built on it are annotated
 * `doc<OrEmpty<Thing>>(...)` so the published schema says so.
 */
export type OrEmpty<T> = T | never[];

/**
 * A single-row response that degenerates to `{}` when the query matches
 * nothing — the other empty-result convention in the Python code, used
 * by handlers that build their response object by hand.
 */
export type OrEmptyObject<T> = T | Record<string, never>;

/**
 * Annotate a route registration.
 *
 * The type argument is the shape of a successful JSON response and is
 * read from the source by the generator, so it must be written
 * explicitly:
 *
 *     app.prot("GET", "/v1/collections", handler,
 *       doc<CollectionSummary[]>({ summary: "Get all collections" }));
 *
 * Routes that do not return JSON (file downloads, zips) leave the type
 * argument off and set `produces` instead.
 */
export function doc<TResponse = unknown>(
  meta: RouteDoc = {},
): RouteDoc & { readonly __response?: TResponse } {
  return meta;
}

/** Document-level metadata, carried over from the Python app so the
 * published spec keeps its identity. */
export const API_INFO = {
  title: "PosdaAPI",
  version: "0.1",
  description: `
This is a complete listing of the Posda API.
This API is used internally by Posda and its various applications,
and can also be used by you.
`.trim(),
} as const;

/** Tag descriptions, keyed by tag name. Tags not listed here are still
 * emitted (derived from the path) but without a description. */
export const API_TAGS: Record<string, string> = {
  Authentication: "Operations related to authorization.",
  Other: "Deprecated, testing, and other non-useful operations. Do not use.",
  Collections: "Retrieve collection info",
};
