// Ports papi/routes/sysstatus.py. This route has no login requirement.

import type { App } from "../server";
import { doc } from "../openapi";
import { pathStr } from "../server";

export function registerSysStatus(app: App): void {
  app.pub("GET", "/v1/sysstatus/system/:system_key", (ctx) => {
    return new Response(
      `<i>Test Message for ${pathStr(ctx, "system_key")}</i>`,
      {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Content-Type": "text/html; charset=utf-8",
        },
      },
    );
  },
    doc({
      summary: "Get Reviewed Percentage For Vr",
    }),
  );
}
