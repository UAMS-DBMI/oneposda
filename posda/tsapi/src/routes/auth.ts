// Ports papi/routes/auth.py.

import type { App } from "../server";
import { jsonResponse } from "../httpx";

export function registerAuth(app: App): void {
  app.pub("POST", "/auth/token", (ctx) => app.auth.login(ctx.req));

  app.prot("GET", "/auth/users/me", (ctx) => jsonResponse(ctx.user));

  app.pub("GET", "/auth/test", () =>
    jsonResponse({ message: "everything looks good" }),
  );
}
