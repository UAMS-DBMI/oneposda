// Ports papi/routes/other.py (test/debug endpoints).

import type { App } from "../server";
import { doc } from "../openapi";
import { pathStr } from "../server";
import { InternalError, jsonResponse } from "../httpx";
import type { User } from "../auth";

export function registerOther(app: App): void {
  app.prot("GET", "/v1/other/streamtest", () => {
    const body = new Uint8Array(150);
    for (let i = 0; i < 50; i++) body.set([1, 2, 3], i * 3);
    return new Response(body, {
      headers: { "Content-Type": "application/octet-stream" },
    });
  },
    doc({
      summary: "Stream Test",
    }),
  );

  app.prot("GET", "/v1/other/tar", () => {
    const body = new Uint8Array(250);
    for (let i = 0; i < 50; i++) body.set([0xab, 0xcd, 0xde, 0xff, i], i * 5);
    return new Response(body, {
      headers: { "Content-Type": "application/octet-stream" },
    });
  },
    doc({
      summary: "Tar Test",
    }),
  );

  app.prot("GET", "/v1/other/asynctar", () => {
    // The Python endpoint calls asynctar.stream(), which does not
    // exist, so it has always responded 500.
    throw new InternalError();
  },
    doc({
      summary: "Asynctar Test",
    }),
  );

  app.prot("GET", "/v1/other/testme", (ctx) => jsonResponse(ctx.user),
    doc<User>({
      summary: "Test Me",
    }),
  );

  app.prot("GET", "/v1/other/query/:query_name/execute", (ctx) => {
    const params: Record<string, string> = {};
    for (const key of new Set(ctx.url.searchParams.keys())) {
      const values = ctx.url.searchParams.getAll(key);
      params[key] = values[values.length - 1]!;
    }
    return jsonResponse({
      query: pathStr(ctx, "query_name"),
      params,
      user: ctx.user,
    });
  },
    doc({
      summary: "Request Test",
    }),
  );
}
