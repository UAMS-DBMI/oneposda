#!/usr/bin/env bun
// Generates the OpenAPI document from the route sources.
//
//     bun scripts/genopenapi.ts
//
// It walks every `app.pub(...)` / `app.prot(...)` call in src/routes/
// with the TypeScript compiler API, reads the `doc<T>({...})` annotation
// attached to each, and resolves T into JSON Schema (scripts/tsschema.ts).
// Nothing is inferred from a running server, so the spec can be built
// without a database.
//
// The same document is written to both implementations: goapi embeds it
// with go:embed, which cannot reach outside its own module, so the Go
// copy is a generated duplicate rather than a symlink. `make openapi`
// rewrites both; CI can re-run it and check that git is clean.

import ts from "typescript";
import { resolve, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import { SchemaBuilder, type Schema } from "./tsschema";
import { API_INFO, API_TAGS, type RouteDoc, type ParamDoc } from "../src/openapi";

const HERE = dirname(fileURLToPath(import.meta.url));
const TSAPI = resolve(HERE, "..");
const OUTPUTS = [
  resolve(TSAPI, "openapi.json"),
  resolve(TSAPI, "../goapi/internal/docs/openapi.json"),
];
/** The Swagger UI page, written next to the vendored assets in both
 * projects so the two implementations serve identical bytes. */
const HTML_OUTPUTS = [
  resolve(TSAPI, "vendor/swagger-ui/docs.html"),
  resolve(TSAPI, "../goapi/internal/docs/swagger-ui/docs.html"),
];

// Asset and spec URLs are relative so that one page works both at /docs
// and at /papi/docs behind the nginx proxy: resolved against a base of
// "/docs" or "/papi/docs", "docs/swagger-ui.css" lands in the right
// place either way.
const DOCS_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PosdaAPI</title>
    <link rel="stylesheet" href="docs/swagger-ui.css" />
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="docs/swagger-ui-bundle.js"></script>
    <script>
      window.ui = SwaggerUIBundle({
        url: "openapi.json",
        dom_id: "#swagger-ui",
        deepLinking: true,
        persistAuthorization: true,
        displayRequestDuration: true,
        tryItOutEnabled: true,
      });
    </script>
  </body>
</html>
`;

/** Route module basename -> tag shown in the UI. */
const TAGS: Record<string, string> = {
  auth: "Authentication",
  other: "Other",
  collections: "Collections",
  studies: "Studies",
  series: "Series",
  files: "Files",
  iecs: "IECs",
  dump: "Dump",
  download: "Download",
  vrstatus: "VRStatus",
  dashboard: "Dashboard",
  rois: "ROIs",
  importer: "Import",
  send_to_public_status: "SendToPublicStatus",
  dicom_roots: "DicomRoots",
  worker: "Worker",
  pathology: "Pathology",
  work: "Work",
  deface: "Deface",
  edits: "Edits",
  nifti: "Nifti",
  sysstatus: "SysStatus",
  masking: "Masking",
  wadors: "WadoRS",
  segs: "Segs",
  activities: "Activities",
  visualreviews: "VisualReviews",
};

interface Route {
  method: string;
  path: string;
  needAuth: boolean;
  module: string;
  doc: RouteDoc;
  response: ts.Type | undefined;
  line: number;
}

function main(): void {
  const program = createProgram();
  const checker = program.getTypeChecker();
  const builder = new SchemaBuilder(checker);

  const routes: Route[] = [];
  for (const sf of program.getSourceFiles()) {
    if (!sf.fileName.includes("/src/routes/")) continue;
    if (sf.fileName.endsWith("/index.ts")) continue;
    collectRoutes(sf, checker, routes);
  }
  routes.sort(
    (a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method),
  );

  const spec = buildSpec(routes, builder);
  const json = JSON.stringify(spec, null, 2) + "\n";
  for (const out of OUTPUTS) {
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, json);
  }
  for (const out of HTML_OUTPUTS) {
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, DOCS_HTML);
  }

  const documented = routes.filter((r) => r.doc.summary).length;
  const typed = routes.filter((r) => r.response).length;
  console.log(
    `${routes.length} routes -> ${Object.keys(spec.paths).length} paths, ` +
      `${builder.components.size} schemas ` +
      `(${documented} with a summary, ${typed} with a response type)`,
  );
  for (const out of OUTPUTS) console.log(`  wrote ${out}`);

  const undocumented = routes.filter((r) => !r.doc.summary && !r.doc.hidden);
  if (undocumented.length) {
    console.log(`\n${undocumented.length} routes still lack a summary:`);
    for (const r of undocumented.slice(0, 20)) {
      console.log(`  ${r.method} ${r.path}  (${r.module}.ts:${r.line})`);
    }
    if (undocumented.length > 20) console.log(`  ... and ${undocumented.length - 20} more`);
  }
}

function createProgram(): ts.Program {
  const configPath = resolve(TSAPI, "tsconfig.json");
  const config = ts.readConfigFile(configPath, ts.sys.readFile);
  if (config.error) {
    throw new Error(ts.flattenDiagnosticMessageText(config.error.messageText, "\n"));
  }
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, TSAPI);
  return ts.createProgram({
    rootNames: parsed.fileNames,
    options: { ...parsed.options, noEmit: true },
  });
}

function collectRoutes(
  sf: ts.SourceFile,
  checker: ts.TypeChecker,
  out: Route[],
): void {
  const module = basename(sf.fileName, ".ts");
  const consts = moduleConsts(sf);

  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
      const fn = node.expression.name.text;
      if (fn === "pub" || fn === "prot") {
        const route = readRegistration(
          node,
          sf,
          checker,
          module,
          fn === "prot",
          consts,
        );
        if (route) out.push(route);
      }
    }
    ts.forEachChild(node, visit);
  };
  ts.forEachChild(sf, visit);
}

function readRegistration(
  node: ts.CallExpression,
  sf: ts.SourceFile,
  checker: ts.TypeChecker,
  module: string,
  needAuth: boolean,
  consts: Consts,
): Route | undefined {
  const [methodArg, pathArg, , docArg] = node.arguments;
  const method = literalString(methodArg);
  const path = literalString(pathArg);
  if (!method || !path) {
    const { line } = sf.getLineAndCharacterOfPosition(node.getStart());
    console.warn(
      `  skipped non-literal registration at ${module}.ts:${line + 1}`,
    );
    return undefined;
  }

  let doc: RouteDoc = {};
  let response: ts.Type | undefined;
  if (docArg && ts.isCallExpression(docArg)) {
    const meta = docArg.arguments[0];
    if (meta && ts.isObjectLiteralExpression(meta)) {
      doc = evalObject(meta, consts) as RouteDoc;
    }
    const typeNode = docArg.typeArguments?.[0];
    if (typeNode) response = checker.getTypeFromTypeNode(typeNode);
  }

  const { line } = sf.getLineAndCharacterOfPosition(node.getStart());
  return { method, path, needAuth, module, doc, response, line: line + 1 };
}

function literalString(node: ts.Expression | undefined): string | undefined {
  if (!node) return undefined;
  if (ts.isStringLiteral(node)) return node.text;
  if (ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  return undefined;
}

/** Module-level `const NAME = <literal>` initializers, so annotations can
 * share a description between several routes without repeating it. */
type Consts = Map<string, ts.Expression>;

function moduleConsts(sf: ts.SourceFile): Consts {
  const out: Consts = new Map();
  for (const stmt of sf.statements) {
    if (!ts.isVariableStatement(stmt)) continue;
    for (const decl of stmt.declarationList.declarations) {
      if (ts.isIdentifier(decl.name) && decl.initializer) {
        out.set(decl.name.text, decl.initializer);
      }
    }
  }
  return out;
}

/** Statically evaluate an object literal of plain JSON-ish values. */
function evalObject(
  node: ts.ObjectLiteralExpression,
  consts: Consts,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const prop of node.properties) {
    if (!ts.isPropertyAssignment(prop)) continue;
    const key = ts.isIdentifier(prop.name)
      ? prop.name.text
      : ts.isStringLiteral(prop.name)
        ? prop.name.text
        : ts.isNumericLiteral(prop.name)
          ? prop.name.text
          : undefined;
    if (key === undefined) continue;
    const value = evalExpr(prop.initializer, consts);
    if (value !== undefined) out[key] = value;
  }
  return out;
}

function evalExpr(node: ts.Expression, consts: Consts, depth = 0): unknown {
  if (depth > 8) return undefined;
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  if (ts.isNumericLiteral(node)) return Number(node.text);
  if (node.kind === ts.SyntaxKind.TrueKeyword) return true;
  if (node.kind === ts.SyntaxKind.FalseKeyword) return false;
  if (node.kind === ts.SyntaxKind.NullKeyword) return null;
  if (ts.isArrayLiteralExpression(node)) {
    return node.elements
      .map((e) => evalExpr(e, consts, depth + 1))
      .filter((v) => v !== undefined);
  }
  if (ts.isObjectLiteralExpression(node)) return evalObject(node, consts);
  if (ts.isParenthesizedExpression(node)) {
    return evalExpr(node.expression, consts, depth + 1);
  }
  // "long text " + "continued" — how multi-line descriptions are written.
  if (
    ts.isBinaryExpression(node) &&
    node.operatorToken.kind === ts.SyntaxKind.PlusToken
  ) {
    const left = evalExpr(node.left, consts, depth + 1);
    const right = evalExpr(node.right, consts, depth + 1);
    if (typeof left === "string" && typeof right === "string") return left + right;
    if (typeof left === "number" && typeof right === "number") return left + right;
    return undefined;
  }
  if (ts.isIdentifier(node)) {
    const target = consts.get(node.text);
    return target ? evalExpr(target, consts, depth + 1) : undefined;
  }
  return undefined;
}

// --- document assembly -------------------------------------------------

interface Spec {
  openapi: string;
  info: Record<string, unknown>;
  servers: { url: string; description?: string }[];
  tags: { name: string; description?: string }[];
  paths: Record<string, Record<string, unknown>>;
  components: Record<string, unknown>;
}

function buildSpec(routes: Route[], builder: SchemaBuilder): Spec {
  const paths: Record<string, Record<string, unknown>> = {};
  const usedTags = new Set<string>();
  const seen = new Set<string>();

  for (const route of routes) {
    if (route.doc.hidden) continue;
    const path = openApiPath(route.path);
    const key = `${route.method} ${path}`;
    // /v1/collections and /v1/collections/ are the same operation.
    if (seen.has(key)) continue;
    seen.add(key);

    const tag = route.doc.tags?.[0] ?? TAGS[route.module] ?? route.module;
    usedTags.add(tag);

    const entry = paths[path] ?? (paths[path] = {});
    entry[route.method.toLowerCase()] = operation(route, tag, builder);
  }

  return {
    openapi: "3.1.0",
    info: { ...API_INFO },
    servers: [
      { url: "/papi", description: "Behind the Posda nginx proxy" },
      { url: "/", description: "Direct access to the API container" },
    ],
    tags: [...usedTags].sort().map((name) => {
      const description = API_TAGS[name];
      return description ? { name, description } : { name };
    }),
    paths,
    components: {
      schemas: {
        ...Object.fromEntries([...builder.components].sort(byKey)),
        HTTPError: {
          type: "object",
          description: "FastAPI-style error body.",
          properties: { detail: { type: "string" } },
          required: ["detail"],
        },
      },
      securitySchemes: {
        OAuth2PasswordBearer: {
          type: "oauth2",
          flows: { password: { tokenUrl: "auth/token", scopes: {} } },
        },
      },
    },
  };
}

function byKey(a: [string, unknown], b: [string, unknown]): number {
  return a[0].localeCompare(b[0]);
}

/** ":id" path segments become "{id}"; Bun wildcards become a catch-all. */
function openApiPath(path: string): string {
  const converted = path
    .split("/")
    .map((seg) => (seg.startsWith(":") ? `{${seg.slice(1)}}` : seg))
    .join("/");
  const trimmed =
    converted.length > 1 && converted.endsWith("/")
      ? converted.slice(0, -1)
      : converted;
  return trimmed.replace("/*", "/{path}");
}

function pathParamNames(path: string): string[] {
  return path
    .split("/")
    .filter((seg) => seg.startsWith(":"))
    .map((seg) => seg.slice(1));
}

function operation(
  route: Route,
  tag: string,
  builder: SchemaBuilder,
): Record<string, unknown> {
  const { doc } = route;
  const inPath = new Set(pathParamNames(route.path));
  const parameters: Record<string, unknown>[] = [];

  // Path parameters first, in the order they appear in the route.
  for (const name of inPath) {
    parameters.push(parameter(name, "path", doc.params?.[name], true));
  }
  for (const [name, meta] of Object.entries(doc.params ?? {})) {
    if (inPath.has(name)) continue;
    parameters.push(parameter(name, "query", meta, meta.required ?? false));
  }

  const success: Record<string, unknown> = {
    description: "Successful Response",
  };
  if (doc.produces) {
    success.content = {
      [doc.produces]: { schema: { type: "string", format: "binary" } },
    };
  } else if (route.response) {
    success.content = {
      "application/json": { schema: builder.schemaFor(route.response) },
    };
  } else {
    success.content = { "application/json": { schema: {} } };
  }

  const responses: Record<string, unknown> = { "200": success };
  if (route.needAuth) responses["401"] = errorResponse("Not authenticated");
  const typedParams = parameters.some(
    (p) => (p.schema as Schema | undefined)?.type === "integer",
  );
  if (typedParams || doc.requestBody) {
    responses["422"] = errorResponse("Validation Error");
  }
  for (const [status, description] of Object.entries(doc.errors ?? {})) {
    responses[status] = errorResponse(description);
  }

  const op: Record<string, unknown> = {
    tags: [tag],
    summary: doc.summary ?? defaultSummary(route),
    operationId: operationId(route),
    responses: Object.fromEntries(
      Object.entries(responses).sort((a, b) => a[0].localeCompare(b[0])),
    ),
  };
  if (doc.description) op.description = doc.description;
  if (doc.deprecated) op.deprecated = true;
  if (parameters.length) op.parameters = parameters;
  if (doc.requestBody) op.requestBody = requestBody(doc.requestBody);
  op.security = route.needAuth ? [{ OAuth2PasswordBearer: [] }] : [];
  return op;
}

function parameter(
  name: string,
  location: "path" | "query",
  meta: ParamDoc | undefined,
  required: boolean,
): Record<string, unknown> {
  const schema: Schema = { type: meta?.type ?? "string" };
  const param: Record<string, unknown> = {
    name,
    in: meta?.in ?? location,
    required: location === "path" ? true : required,
    schema,
  };
  if (meta?.description) param.description = meta.description;
  if (meta?.example !== undefined) param.example = meta.example;
  return param;
}

function requestBody(body: NonNullable<RouteDoc["requestBody"]>): unknown {
  const contentType = body.contentType ?? "application/json";
  const properties: Record<string, Schema> = {};
  const required: string[] = [];
  for (const [name, field] of Object.entries(body.fields ?? {})) {
    const schema: Schema = { type: field.type ?? "string" };
    if (field.description) schema.description = field.description;
    properties[name] = schema;
    if (field.required) required.push(name);
  }
  const schema: Schema = { type: "object" };
  if (Object.keys(properties).length) schema.properties = properties;
  if (required.length) schema.required = required;

  const out: Record<string, unknown> = {
    required: body.required ?? true,
    content: { [contentType]: { schema } },
  };
  if (body.description) out.description = body.description;
  return out;
}

function errorResponse(description: string): Record<string, unknown> {
  return {
    description,
    content: {
      "application/json": { schema: { $ref: "#/components/schemas/HTTPError" } },
    },
  };
}

function defaultSummary(route: Route): string {
  const last =
    route.path
      .split("/")
      .filter((s) => s && !s.startsWith(":"))
      .pop() ?? route.module;
  return `${route.method} ${last}`;
}

/** Stable, unique id derived from method and path, like FastAPI's. */
function operationId(route: Route): string {
  const slug = route.path
    .replace(/[:{}]/g, "")
    .split("/")
    .filter(Boolean)
    .join("_")
    .replace(/[^A-Za-z0-9_]/g, "_");
  return `${route.method.toLowerCase()}_${slug || "root"}`;
}

main();
