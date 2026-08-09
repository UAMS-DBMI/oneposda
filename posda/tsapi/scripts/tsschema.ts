// TypeScript type -> JSON Schema.
//
// Used by genopenapi.ts to turn the response interfaces declared next to
// each query into schemas. Only the constructs the route modules
// actually use are supported; anything unrecognised degrades to `{}`
// ("any JSON"), which is honest rather than wrong.

import ts from "typescript";

export interface Schema {
  $ref?: string;
  type?: string | string[];
  format?: string;
  items?: Schema;
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: Schema | boolean;
  enum?: unknown[];
  anyOf?: Schema[];
  description?: string;
  nullable?: boolean;
}

/** Named schemas hoisted into components/schemas, keyed by schema name. */
export type Components = Map<string, Schema>;

export class SchemaBuilder {
  readonly components: Components = new Map();
  /** Symbol -> component name, so the same interface reuses one entry. */
  private names = new Map<ts.Symbol, string>();
  /** Names currently being built, to break recursive types. */
  private building = new Set<string>();

  constructor(private readonly checker: ts.TypeChecker) {}

  /** The schema for a type, hoisting named object types into components. */
  schemaFor(type: ts.Type): Schema {
    return this.build(type, 0);
  }

  private build(type: ts.Type, depth: number): Schema {
    if (depth > 12) return {};
    const f = type.flags;

    if (f & ts.TypeFlags.Any || f & ts.TypeFlags.Unknown) return {};
    if (f & ts.TypeFlags.Never) return {};
    if (f & ts.TypeFlags.Void || f & ts.TypeFlags.Undefined) return {};
    if (f & ts.TypeFlags.Null) return { type: "null" };
    if (f & ts.TypeFlags.StringLiteral) {
      return { type: "string", enum: [(type as ts.StringLiteralType).value] };
    }
    if (f & ts.TypeFlags.NumberLiteral) {
      return { type: "number", enum: [(type as ts.NumberLiteralType).value] };
    }
    if (f & ts.TypeFlags.BooleanLiteral) return { type: "boolean" };
    if (f & ts.TypeFlags.String) return { type: "string" };
    if (f & ts.TypeFlags.Number) return { type: "number" };
    if (f & ts.TypeFlags.BigInt) return { type: "integer" };
    if (f & ts.TypeFlags.Boolean) return { type: "boolean" };
    if (f & ts.TypeFlags.ESSymbol) return {};

    if (type.isUnion()) return this.buildUnion(type, depth);
    if (type.isIntersection()) {
      // Interfaces that `extend` another arrive here only when the
      // checker cannot merge them; approximate by merging properties.
      return this.buildObject(type, depth);
    }

    const named = this.wellKnown(type);
    if (named) return named;

    if (this.checker.isArrayType(type)) {
      const [elem] = this.checker.getTypeArguments(type as ts.TypeReference);
      return { type: "array", items: elem ? this.build(elem, depth + 1) : {} };
    }
    if (this.checker.isTupleType(type)) {
      const args = this.checker.getTypeArguments(type as ts.TypeReference);
      return {
        type: "array",
        items: args.length ? this.build(args[0]!, depth + 1) : {},
      };
    }

    if (f & ts.TypeFlags.Object) return this.namedObject(type, depth);
    return {};
  }

  private buildUnion(type: ts.UnionType, depth: number): Schema {
    const parts: Schema[] = [];
    let nullable = false;
    let sawTrue = false;
    let sawFalse = false;

    for (const member of type.types) {
      if (member.flags & (ts.TypeFlags.Null | ts.TypeFlags.Undefined)) {
        nullable = true;
        continue;
      }
      // `boolean` is modelled as the union true | false.
      if (member.flags & ts.TypeFlags.BooleanLiteral) {
        const intrinsic = (member as unknown as { intrinsicName?: string })
          .intrinsicName;
        if (intrinsic === "true") sawTrue = true;
        if (intrinsic === "false") sawFalse = true;
        continue;
      }
      parts.push(this.build(member, depth + 1));
    }
    if (sawTrue && sawFalse) parts.push({ type: "boolean" });
    else if (sawTrue || sawFalse) parts.push({ type: "boolean" });

    return finishUnion(parts, nullable);
  }

  /** Types the route modules use that have no useful structural form. */
  private wellKnown(type: ts.Type): Schema | undefined {
    const name = type.getSymbol()?.getName();
    switch (name) {
      case "PyFloat":
        // A float wrapper; serialises as a JSON number.
        return { type: "number" };
      case "Date":
        return { type: "string", format: "date-time" };
      case "Buffer":
      case "Uint8Array":
      case "ArrayBuffer":
      case "Blob":
        return { type: "string", format: "binary" };
      case "Response":
      case "ReadableStream":
        return {};
      default:
        return undefined;
    }
  }

  /** An object type: hoisted to components when it has a usable name. */
  private namedObject(type: ts.Type, depth: number): Schema {
    const symbol = type.aliasSymbol ?? type.getSymbol();
    const raw = symbol?.getName();
    const anonymous =
      !raw || raw === "__type" || raw === "__object" || raw === "Object";

    if (anonymous || !symbol) return this.buildObject(type, depth);

    let name = this.names.get(symbol);
    if (!name) {
      name = this.uniqueName(raw, symbol);
      this.names.set(symbol, name);
      this.building.add(name);
      // Reserve the slot before recursing so self-referential types stop.
      this.components.set(name, {});
      const built = this.buildObject(type, depth);
      const doc = docComment(symbol);
      this.components.set(name, doc ? { description: doc, ...built } : built);
      this.building.delete(name);
    }
    return { $ref: `#/components/schemas/${name}` };
  }

  private uniqueName(raw: string, symbol: ts.Symbol): string {
    if (!this.components.has(raw)) return raw;
    // Two modules declaring the same interface name: qualify with the
    // file it came from (Row -> WorkRow) rather than Row2.
    const file = symbol.declarations?.[0]?.getSourceFile().fileName ?? "";
    const base = file.split("/").pop()?.replace(/\.ts$/, "") ?? "";
    const prefix = base
      .split("_")
      .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
      .join("");
    let candidate = prefix + raw;
    let n = 2;
    while (this.components.has(candidate)) candidate = `${prefix}${raw}${n++}`;
    return candidate;
  }

  private buildObject(type: ts.Type, depth: number): Schema {
    const schema: Schema = { type: "object" };
    const properties: Record<string, Schema> = {};
    const required: string[] = [];

    for (const prop of this.checker.getPropertiesOfType(type)) {
      const decl = prop.valueDeclaration ?? prop.declarations?.[0];
      const propType = decl
        ? this.checker.getTypeOfSymbolAtLocation(prop, decl)
        : this.checker.getDeclaredTypeOfSymbol(prop);
      const sub = this.build(propType, depth + 1);
      const doc = docComment(prop);
      properties[prop.getName()] = doc ? { description: doc, ...sub } : sub;
      if (!(prop.flags & ts.SymbolFlags.Optional)) required.push(prop.getName());
    }

    // Record<string, X> and index signatures.
    const index =
      this.checker.getIndexInfoOfType(type, ts.IndexKind.String) ?? undefined;
    if (index) {
      schema.additionalProperties = this.build(index.type, depth + 1);
    }

    if (Object.keys(properties).length) schema.properties = properties;
    if (required.length) schema.required = required;
    return schema;
  }
}

function finishUnion(parts: Schema[], nullable: boolean): Schema {
  const unique = dedupe(parts);
  if (unique.length === 0) return nullable ? { type: "null" } : {};
  if (unique.length === 1) {
    const only = unique[0]!;
    if (!nullable) return only;
    // OpenAPI 3.1 uses a type array for nullability; a $ref cannot carry
    // one, so wrap it.
    if (only.$ref) return { anyOf: [only, { type: "null" }] };
    if (typeof only.type === "string") return { ...only, type: [only.type, "null"] };
    return { anyOf: [only, { type: "null" }] };
  }
  return { anyOf: nullable ? [...unique, { type: "null" }] : unique };
}

function dedupe(parts: Schema[]): Schema[] {
  const seen = new Set<string>();
  const out: Schema[] = [];
  for (const p of parts) {
    const key = JSON.stringify(p);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  return out;
}

/** The leading JSDoc/line comment of a declaration, as a description.
 *
 * The row interfaces are labelled with the route they belong to
 * ("GET /v1/iecs/{iec} — image_equivalence_class rows."). The route is
 * already obvious from where the schema is referenced, so only the prose
 * after it is kept. */
function docComment(symbol: ts.Symbol): string | undefined {
  const parts = symbol.getDocumentationComment(undefined);
  const text = ts.displayPartsToString(parts).trim();
  if (!text.length) return undefined;
  const stripped = text
    .replace(
      /^(?:(?:GET|POST|PUT|DELETE|PATCH)\s+\S+|\.\.\.\/\S+)(?:\s+and\s+\S+)*\s*/,
      "",
    )
    // "elements" / "rows" only said which route the interface serves.
    .replace(/^(?:elements|rows)\b\s*/i, "")
    .replace(/^(?:[—–-]|:)\s*/, "")
    .trim();
  // What is left has to say something; "." and "*" do not.
  return /[A-Za-z]{3}/.test(stripped) ? stripped : undefined;
}
