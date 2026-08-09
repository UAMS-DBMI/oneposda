// Invariants of the generated OpenAPI document.
//
// These run without a server or a database: they check the checked-in
// document is internally consistent and that the copy the Go port embeds
// is identical. `make openapi-check` separately verifies it is not
// stale with respect to the sources.

import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(import.meta.dir, "..");
const raw = readFileSync(resolve(ROOT, "openapi.json"), "utf8");
const spec = JSON.parse(raw);

const operations: [string, string, any][] = Object.entries<any>(spec.paths)
  .flatMap(([path, methods]) =>
    Object.entries<any>(methods).map(
      ([method, op]) => [path, method, op] as [string, string, any],
    ),
  );

describe("openapi document", () => {
  test("is an OpenAPI 3.1 document with the Posda identity", () => {
    expect(spec.openapi).toBe("3.1.0");
    expect(spec.info.title).toBe("PosdaAPI");
    expect(spec.servers.map((s: any) => s.url)).toContain("/papi");
  });

  test("covers every route module", () => {
    const tags = new Set(spec.tags.map((t: any) => t.name));
    for (const name of ["Collections", "Files", "Masking", "WadoRS", "Import"]) {
      expect(tags).toContain(name);
    }
  });

  test("every operation has a summary, an id and responses", () => {
    for (const [path, method, op] of operations) {
      const where = `${method.toUpperCase()} ${path}`;
      expect(op.summary, where).toBeTruthy();
      expect(op.operationId, where).toBeTruthy();
      expect(op.responses?.["200"], where).toBeTruthy();
      // security is [] for public routes and non-empty for protected
      // ones, but it always has to be stated.
      expect(Array.isArray(op.security), where).toBe(true);
    }
  });

  test("operation ids are unique", () => {
    const ids = operations.map(([, , op]) => op.operationId);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test("protected operations document a 401", () => {
    for (const [path, method, op] of operations) {
      if (!op.security?.length) continue;
      expect(op.responses["401"], `${method.toUpperCase()} ${path}`).toBeTruthy();
    }
  });

  test("path parameters are declared for every path template", () => {
    for (const [path, method, op] of operations) {
      const names = [...path.matchAll(/\{([^}]+)\}/g)].map((m) => m[1]);
      const declared = new Set(
        (op.parameters ?? [])
          .filter((p: any) => p.in === "path")
          .map((p: any) => p.name),
      );
      for (const name of names) {
        expect(declared, `${method.toUpperCase()} ${path} / ${name}`).toContain(
          name,
        );
      }
    }
  });

  test("every $ref resolves", () => {
    const refs = [...raw.matchAll(/"\$ref":\s*"([^"]+)"/g)].map((m) => m[1]!);
    expect(refs.length).toBeGreaterThan(0);
    for (const ref of refs) {
      expect(ref.startsWith("#/components/schemas/"), ref).toBe(true);
      const name = ref.split("/").pop()!;
      expect(spec.components.schemas[name], ref).toBeDefined();
    }
  });

  test("no schema is left as a bare $ref placeholder", () => {
    for (const [name, schema] of Object.entries<any>(spec.components.schemas)) {
      expect(Object.keys(schema).length, name).toBeGreaterThan(0);
    }
  });

  test("the copy embedded by the Go port is identical", () => {
    const go = readFileSync(
      resolve(ROOT, "../goapi/internal/docs/openapi.json"),
      "utf8",
    );
    expect(go).toBe(raw);
  });

  test("both ports serve the same Swagger UI page", () => {
    const ts = readFileSync(resolve(ROOT, "vendor/swagger-ui/docs.html"), "utf8");
    const go = readFileSync(
      resolve(ROOT, "../goapi/internal/docs/swagger-ui/docs.html"),
      "utf8",
    );
    expect(go).toBe(ts);
    // Asset URLs must stay relative so /papi/docs works behind nginx.
    expect(ts).toContain('href="docs/swagger-ui.css"');
    expect(ts).toContain('url: "openapi.json"');
  });
});
