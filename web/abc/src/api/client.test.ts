import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ForbiddenError, UnauthorizedError, api } from "./client";

function respond(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
  });
}

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends JSON with same-origin credentials and parses the reply", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(200, { ok: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.post<{ ok: number }>("/v1/abc/x", { a: 1 });

    expect(result).toEqual({ ok: 1 });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/papi/v1/abc/x");
    expect(init.credentials).toBe("same-origin");
    expect(init.body).toBe('{"a":1}');
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(204)));
    await expect(api.put("/v1/abc/me/bindings/x", { value: "1" })).resolves.toBeUndefined();
  });

  it("maps 401 and 403 to typed errors with the detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(respond(401, { detail: "Invalid authentication credentials" })),
    );
    await expect(api.get("/v1/abc/me")).rejects.toBeInstanceOf(UnauthorizedError);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(403, { detail: "nope" })));
    const error = await api.get("/v1/abc/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ForbiddenError);
    expect((error as ForbiddenError).detail).toBe("nope");
  });

  it("uses the status text when the body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("boom", { status: 502, statusText: "Bad Gateway" })),
    );
    const error = await api.get("/v1/abc/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).detail).toBe("Bad Gateway");
  });
});
