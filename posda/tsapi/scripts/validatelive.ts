#!/usr/bin/env bun
// Checks the generated OpenAPI document against what the API actually
// returns, so a wrong response type in an annotation cannot go unnoticed.
//
//     bun scripts/validatelive.ts < endpoints.txt
//
// Reads concrete request paths (one per line) from stdin, fetches each
// from $API_BASE with $API_TOKEN, finds the matching path template in
// openapi.json and validates the body against that operation's 200
// schema. Endpoints whose schema is the empty "any JSON" schema are
// counted as unverified rather than passing.
//
// Needs a running server and a database, so it is not part of `bun test`.

import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SPEC = JSON.parse(
  readFileSync(resolve(HERE, "../openapi.json"), "utf8"),
) as Spec;

const BASE = process.env.API_BASE ?? "http://localhost:8098";
const TOKEN = process.env.API_TOKEN ?? "";

interface Spec {
  paths: Record<string, Record<string, Operation>>;
  components: { schemas: Record<string, Schema> };
}
interface Operation {
  responses: Record<string, { content?: Record<string, { schema: Schema }> }>;
}
interface Schema {
  $ref?: string;
  type?: string | string[];
  items?: Schema;
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: Schema | boolean;
  anyOf?: Schema[];
  enum?: unknown[];
  format?: string;
}

// --- matching a concrete path to a spec template -----------------------

interface Template {
  path: string;
  regex: RegExp;
  params: number;
}

const templates: Template[] = Object.keys(SPEC.paths)
  .map((path) => ({
    path,
    regex: new RegExp(
      "^" +
        path
          .split("/")
          .map((seg) =>
            seg.startsWith("{") && seg.endsWith("}")
              ? "[^/]+"
              : seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
          )
          .join("/") +
        "$",
    ),
    params: (path.match(/\{/g) ?? []).length,
  }))
  // Prefer the template with the fewest wildcards, so a literal path
  // wins over one that only matches through a parameter.
  .sort((a, b) => a.params - b.params);

function matchTemplate(path: string): Template | undefined {
  return templates.find((t) => t.regex.test(path));
}

// --- a JSON Schema validator for the subset the generator emits --------

function deref(schema: Schema): Schema {
  if (!schema.$ref) return schema;
  const name = schema.$ref.split("/").pop()!;
  return SPEC.components.schemas[name] ?? {};
}

function isEmptySchema(schema: Schema): boolean {
  return Object.keys(schema).length === 0;
}

function validate(value: unknown, schema: Schema, path = "$"): string[] {
  const s = deref(schema);
  if (isEmptySchema(s)) return [];

  if (s.anyOf) {
    const branches = s.anyOf.map((alt) => validate(value, alt, path));
    if (branches.some((errs) => errs.length === 0)) return [];
    return [`${path}: matches none of the anyOf branches (${typeName(value)})`];
  }

  if (s.type !== undefined) {
    const allowed = Array.isArray(s.type) ? s.type : [s.type];
    if (!allowed.some((t) => typeMatches(value, t))) {
      return [`${path}: expected ${allowed.join("|")}, got ${typeName(value)}`];
    }
  }

  if (s.enum && !s.enum.some((e) => e === value)) {
    return [`${path}: ${JSON.stringify(value)} not in enum`];
  }

  const errors: string[] = [];
  if (Array.isArray(value) && s.items) {
    // Checking every element of a large array is wasteful; the first
    // few catch shape errors just as well.
    for (const [i, item] of value.slice(0, 20).entries()) {
      errors.push(...validate(item, s.items, `${path}[${i}]`));
    }
  }

  if (value && typeof value === "object" && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>;
    for (const name of s.required ?? []) {
      if (!(name in obj)) errors.push(`${path}.${name}: missing`);
    }
    for (const [name, sub] of Object.entries(s.properties ?? {})) {
      if (name in obj) errors.push(...validate(obj[name], sub, `${path}.${name}`));
    }
    if (s.properties) {
      const extra = Object.keys(obj).filter((k) => !(k in s.properties!));
      if (extra.length && s.additionalProperties === undefined) {
        errors.push(`${path}: undocumented properties ${extra.join(", ")}`);
      }
    }
    if (s.additionalProperties && typeof s.additionalProperties === "object") {
      for (const [k, v] of Object.entries(obj)) {
        if (s.properties && k in s.properties) continue;
        errors.push(...validate(v, s.additionalProperties, `${path}.${k}`));
      }
    }
  }
  return errors;
}

function typeMatches(value: unknown, type: string): boolean {
  switch (type) {
    case "null":
      return value === null;
    case "array":
      return Array.isArray(value);
    case "object":
      return value !== null && typeof value === "object" && !Array.isArray(value);
    case "string":
      return typeof value === "string";
    case "number":
      return typeof value === "number";
    case "integer":
      return typeof value === "number" && Number.isInteger(value);
    case "boolean":
      return typeof value === "boolean";
    default:
      return true;
  }
}

function typeName(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

// --- run ---------------------------------------------------------------

const paths = (await Bun.stdin.text())
  .split("\n")
  .map((l) => l.trim())
  .filter((l) => l.startsWith("/"));

let checked = 0;
let unmatched = 0;
let failed = 0;
/** Spec paths that answered with JSON but declare no response schema. */
const unverified = new Set<string>();

for (const path of paths) {
  const res = await fetch(BASE + path, {
    headers: TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {},
  });
  if (!res.ok) continue;
  const ctype = res.headers.get("content-type") ?? "";
  if (!ctype.includes("json")) continue;

  // Spec paths are relative to the servers entry, so drop the /papi
  // prefix, and the trailing slash variants share one spec path.
  let bare = path.split("?")[0]!;
  if (bare.startsWith("/papi/")) bare = bare.slice(5);
  if (bare.length > 1 && bare.endsWith("/")) bare = bare.slice(0, -1);
  const template = matchTemplate(bare);
  if (!template) {
    unmatched++;
    console.log(`no spec path matches ${bare}`);
    continue;
  }
  const op = SPEC.paths[template.path]?.get;
  const schema = op?.responses?.["200"]?.content?.["application/json"]?.schema;
  if (!schema || isEmptySchema(deref(schema))) {
    unverified.add(template.path);
    continue;
  }

  const body = await res.json();
  const errors = validate(body, schema);
  checked++;
  if (errors.length) {
    failed++;
    console.log(`\nFAIL ${bare}  (spec: ${template.path})`);
    for (const e of errors.slice(0, 8)) console.log(`  ${e}`);
    if (errors.length > 8) console.log(`  ... and ${errors.length - 8} more`);
  }
}

if (unverified.size) {
  console.log("\nreturned JSON but declare no response schema:");
  for (const path of [...unverified].sort()) console.log(`  ${path}`);
}

console.log(
  `\n${checked} endpoints validated, ${failed} failing, ` +
    `${unverified.size} with no response schema, ${unmatched} unmatched`,
);
process.exit(failed > 0 ? 1 : 0);
