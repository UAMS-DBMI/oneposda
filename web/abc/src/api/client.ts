/** Thin fetch wrapper for the Posda API, relying on the logintoken cookie. */

export const API_BASE = "/papi";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export class UnauthorizedError extends ApiError {
  constructor(detail: string) {
    super(401, detail);
    this.name = "UnauthorizedError";
  }
}

export class ForbiddenError extends ApiError {
  constructor(detail: string) {
    super(403, detail);
    this.name = "ForbiddenError";
  }
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

async function detailOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail !== undefined) return JSON.stringify(body.detail);
  } catch {
    // not JSON; fall through to the status text
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin" };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const response = await fetch(API_BASE + path, init);
  if (response.status === 401) throw new UnauthorizedError(await detailOf(response));
  if (response.status === 403) throw new ForbiddenError(await detailOf(response));
  if (!response.ok) throw new ApiError(response.status, await detailOf(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

/** SWR fetcher: the key is the API path, e.g. "/v1/abc/me". */
export function swrFetcher<T>(path: string): Promise<T> {
  return api.get<T>(path);
}
