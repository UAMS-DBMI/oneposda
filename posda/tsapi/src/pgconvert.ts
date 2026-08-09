// Conversion of Bun.sql-decoded column values into the JSON-ready
// values FastAPI produced from asyncpg records.
//
// Bun's Postgres client does not expose result column type OIDs, so
// unlike the Go implementation (which converts generically from pgx
// field descriptions) each query declares which of its columns need
// special decoding via a `Convs` map. Columns holding text, integers,
// booleans and uuids need no entry. The conventions per type:
//
//   date         Date (UTC midnight)        -> "2007-02-28"
//   timestamp    select as `col::text`      -> "2007-02-28T11:12:59[.ffffff]"
//   timestamptz  select as `col::text`      -> UTC with "+00:00" offset
//                (connections pin TimeZone=UTC so the text is UTC)
//   time         text                       -> "11:12:59[.ffffff]"
//   interval     text ("1 day 02:00:00")    -> total seconds as a float,
//                with months counted as 30 days (asyncpg's timedelta)
//   numeric      text                       -> int when there is no
//                fractional part, else float ("0.000000" -> 0.0)
//   float4/8     number                     -> PyFloat (keeps ".0")
//   json/jsonb   select as `col::text`      -> raw text, no entry needed
//   int8         text                       -> number (bigint if unsafe)
//   bytea        Buffer                     -> utf-8 string
//
// "T[]" variants apply T to each element of an array column.

import { PyFloat } from "./pyjson";

export type Conv =
  | "date"
  | "ts"
  | "tstz"
  | "time"
  | "interval"
  | "num"
  | "float"
  | "int8"
  | "bytea"
  | "date[]"
  | "ts[]"
  | "num[]"
  | "float[]"
  | "int8[]";

/** Map of column name -> conversion for the columns that need one. */
export type Convs = Record<string, Conv>;

export function pgDate(v: Date): string {
  return v.toISOString().slice(0, 10);
}

/** Pad a fractional-seconds part to Python's 6 digits. */
function padFraction(frac: string | undefined): string {
  if (!frac) return "";
  return "." + frac.padEnd(6, "0");
}

const tsRe = /^(\d{4,}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?$/;

/** Postgres timestamp text -> Python naive isoformat. */
export function pgTimestampText(v: string): string {
  const m = tsRe.exec(v);
  if (!m) return v;
  return `${m[1]}T${m[2]}${padFraction(m[3])}`;
}

const tstzRe =
  /^(\d{4,}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?([+-]\d{2})(?::(\d{2}))?$/;

/** Postgres timestamptz text -> Python aware isoformat ("+00:00"). */
export function pgTimestamptzText(v: string): string {
  const m = tstzRe.exec(v);
  if (!m) return v;
  return `${m[1]}T${m[2]}${padFraction(m[3])}${m[4]}:${m[5] ?? "00"}`;
}

const timeRe = /^(\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?$/;

export function pgTimeText(v: string): string {
  const m = timeRe.exec(v);
  if (!m) return v;
  return `${m[1]}${padFraction(m[2])}`;
}

const intervalRe =
  /^(?:(-?\d+)\s+years?\s*)?(?:(-?\d+)\s+mons?\s*)?(?:(-?\d+)\s+days?\s*)?(?:([+-]?)(\d+):(\d{2}):(\d{2})(?:\.(\d{1,6}))?)?$/;

/**
 * Postgres interval text (IntervalStyle 'postgres') -> total seconds as
 * a float, mirroring asyncpg's interval->timedelta conversion followed
 * by timedelta.total_seconds() (months count as 30 days).
 */
export function pgIntervalSeconds(v: string): PyFloat | null {
  const m = intervalRe.exec(v.trim());
  if (!m) return null;
  const years = Number(m[1] ?? 0);
  const mons = Number(m[2] ?? 0);
  const days = Number(m[3] ?? 0);
  const sign = m[4] === "-" ? -1 : 1;
  const hms =
    Number(m[5] ?? 0) * 3600 +
    Number(m[6] ?? 0) * 60 +
    Number(m[7] ?? 0) +
    Number(m[8] ? `0.${m[8]}` : 0);
  const totalDays = (years * 12 + mons) * 30 + days;
  return new PyFloat(totalDays * 86400 + sign * hms);
}

/**
 * Numeric text -> int when the value has no fractional digits, float
 * otherwise (pydantic's decimal_encoder; "0.000000" is a float).
 */
export function pgNumericText(v: string): number | PyFloat | bigint | null {
  if (v === "NaN" || v === "Infinity" || v === "-Infinity") return null;
  if (!/[.eE]/.test(v)) {
    const n = Number(v);
    return Number.isSafeInteger(n) ? n : BigInt(v);
  }
  return new PyFloat(Number.parseFloat(v));
}

export function pgInt8Text(v: string): number | bigint {
  const n = Number(v);
  return Number.isSafeInteger(n) ? n : BigInt(v);
}

function convertOne(conv: Conv, v: unknown): unknown {
  if (v === null || v === undefined) return null;
  switch (conv) {
    case "date":
      return v instanceof Date ? pgDate(v) : v;
    case "ts":
      return typeof v === "string" ? pgTimestampText(v) : v;
    case "tstz":
      return typeof v === "string" ? pgTimestamptzText(v) : v;
    case "time":
      return typeof v === "string" ? pgTimeText(v) : v;
    case "interval":
      return typeof v === "string" ? pgIntervalSeconds(v) : v;
    case "num":
      return typeof v === "string" ? pgNumericText(v) : v;
    case "float":
      return typeof v === "number" ? new PyFloat(v) : v;
    case "int8":
      return typeof v === "string" ? pgInt8Text(v) : v;
    case "bytea":
      return v instanceof Uint8Array ? Buffer.from(v).toString("utf8") : v;
    case "date[]":
    case "ts[]":
    case "num[]":
    case "float[]":
    case "int8[]": {
      const elem = conv.slice(0, -2) as Conv;
      return Array.isArray(v) ? v.map((x) => convertOne(elem, x)) : v;
    }
  }
}

/** Apply per-column conversions to a result row, in place. */
export function convertRow(row: Record<string, unknown>, convs?: Convs): void {
  if (!convs) return;
  for (const [col, conv] of Object.entries(convs)) {
    if (col in row) row[col] = convertOne(conv, row[col]);
  }
}
