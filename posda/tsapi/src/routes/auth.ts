// Ports papi/routes/auth.py.

import type { App } from "../server";
import { doc } from "../openapi";
import { jsonResponse } from "../httpx";

export function registerAuth(app: App): void {
  app.pub("POST", "/auth/token", (ctx) => app.auth.login(ctx.req),
    doc({
      summary: "Login",
      requestBody: {
        contentType: "application/x-www-form-urlencoded",
        fields: {
          grant_type: {  },
          username: { required: true },
          password: { required: true },
          scope: {  },
          client_id: {  },
          client_secret: {  },
        },
      },
    }),
  );

  app.prot("GET", "/auth/users/me", (ctx) => jsonResponse(ctx.user),
    doc({
      summary: "Read Users Me",
      description: "Get the current logged in user",
    }),
  );

  app.pub("GET", "/auth/test", () =>
    jsonResponse({ message: "everything looks good" }),
    doc({
      summary: "Testpoint",
    }),
  );
}
