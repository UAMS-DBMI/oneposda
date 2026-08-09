// The OpenAPI document and its Swagger UI.
//
// The Python implementation got these from FastAPI for free; both ports
// generate the document at build time instead (scripts/genopenapi.ts)
// and serve the result as a static asset. The UI is vendored rather than
// loaded from a CDN so /docs works in deployments without outbound
// internet access.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { App } from "../server";
import { doc } from "../openapi";

const ASSET_ROOT = fileURLToPath(new URL("../../", import.meta.url));

/** Read once at startup: the spec and the UI never change at runtime. */
function asset(relative: string): Buffer {
  return readFileSync(ASSET_ROOT + relative);
}

/** A year — the assets are versioned by the image they ship in. */
const ASSET_CACHE = "public, max-age=31536000, immutable";

export function registerDocs(app: App): void {
  const spec = asset("openapi.json");
  const html = asset("vendor/swagger-ui/docs.html");
  const css = asset("vendor/swagger-ui/swagger-ui.css");
  const js = asset("vendor/swagger-ui/swagger-ui-bundle.js");

  app.pub(
    "GET",
    "/openapi.json",
    () => staticResponse(spec, "application/json"),
    doc({ summary: "OpenAPI document", hidden: true }),
  );
  app.pub(
    "GET",
    "/docs",
    () => staticResponse(html, "text/html; charset=utf-8"),
    doc({ summary: "Swagger UI", hidden: true }),
  );
  app.pub(
    "GET",
    "/docs/swagger-ui.css",
    () => staticResponse(css, "text/css", ASSET_CACHE),
    doc({ summary: "Swagger UI stylesheet", hidden: true }),
  );
  app.pub(
    "GET",
    "/docs/swagger-ui-bundle.js",
    () => staticResponse(js, "application/javascript", ASSET_CACHE),
    doc({ summary: "Swagger UI bundle", hidden: true }),
  );
}

function staticResponse(
  body: Buffer,
  contentType: string,
  cacheControl?: string,
): Response {
  const headers: Record<string, string> = { "Content-Type": contentType };
  if (cacheControl) headers["Cache-Control"] = cacheControl;
  return new Response(body as unknown as BodyInit, { headers });
}
