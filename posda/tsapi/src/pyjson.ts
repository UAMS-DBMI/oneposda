// JSON serialization matching what FastAPI produces from asyncpg
// records (see the Go implementation's internal/db/convert.go and the
// README "Serialization parity" section):
//
//   - floats print Python-style: integral values keep a trailing ".0"
//   - NaN / Infinity serialize as null
//   - compact separators, no HTML escaping
//
// JavaScript numbers cannot distinguish 1 from 1.0, so values decoded
// from float / numeric-with-scale columns are wrapped in PyFloat, which
// this serializer renders Python-style. PyFloat has a valueOf() so
// arithmetic and comparisons in handlers still work.

/** A float that serializes like Python's json module prints floats. */
export class PyFloat {
  constructor(public readonly value: number) {}
  valueOf(): number {
    return this.value;
  }
}

export function pyFloatString(v: number): string {
  if (Number.isNaN(v) || !Number.isFinite(v)) return "null";
  const s = String(v);
  return /[.eE]/.test(s) ? s : s + ".0";
}

/**
 * Serialize a value to JSON. Behaves like JSON.stringify (compact, no
 * HTML escaping) except for the Python float conventions above. Plain
 * non-integral numbers also render as floats (handler-computed math);
 * integral floats must be wrapped in PyFloat to keep their ".0".
 */
export function pyJson(v: unknown): string {
  if (v === null || v === undefined) return "null";
  switch (typeof v) {
    case "boolean":
      return v ? "true" : "false";
    case "string":
      return JSON.stringify(v);
    case "number":
      if (Number.isNaN(v) || !Number.isFinite(v)) return "null";
      return Number.isInteger(v) ? String(v) : pyFloatString(v);
    case "bigint":
      return v.toString();
    case "object":
      break;
    default:
      throw new TypeError(`cannot serialize ${typeof v} to JSON`);
  }
  if (v instanceof PyFloat) return pyFloatString(v.value);
  if (Array.isArray(v)) return "[" + v.map(pyJson).join(",") + "]";
  // Plain objects: insertion order is preserved, matching Python dicts.
  const parts: string[] = [];
  for (const [k, val] of Object.entries(v)) {
    if (val === undefined) continue;
    parts.push(JSON.stringify(k) + ":" + pyJson(val));
  }
  return "{" + parts.join(",") + "}";
}
