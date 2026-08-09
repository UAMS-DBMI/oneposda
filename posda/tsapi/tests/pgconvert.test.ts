import { describe, expect, test } from "bun:test";
import {
  pgDate,
  pgIntervalSeconds,
  pgNumericText,
  pgTimeText,
  pgTimestampText,
  pgTimestamptzText,
  convertRow,
} from "../src/pgconvert";
import { PyFloat, pyJson } from "../src/pyjson";

describe("timestamp text conversion", () => {
  test("no fraction", () => {
    expect(pgTimestampText("2007-02-28 11:12:59")).toBe("2007-02-28T11:12:59");
  });
  test("fraction padded to 6 digits", () => {
    expect(pgTimestampText("2007-02-28 11:12:59.5")).toBe(
      "2007-02-28T11:12:59.500000",
    );
    expect(pgTimestampText("2007-02-28 11:12:59.123456")).toBe(
      "2007-02-28T11:12:59.123456",
    );
  });
  test("timestamptz gets +00:00 offset", () => {
    expect(pgTimestamptzText("2026-08-03 22:52:31.157376+00")).toBe(
      "2026-08-03T22:52:31.157376+00:00",
    );
    expect(pgTimestamptzText("2026-08-03 22:52:31+00")).toBe(
      "2026-08-03T22:52:31+00:00",
    );
  });
});

describe("time text conversion", () => {
  test("pads fraction", () => {
    expect(pgTimeText("11:12:59.5")).toBe("11:12:59.500000");
    expect(pgTimeText("11:12:59")).toBe("11:12:59");
  });
});

describe("interval conversion (asyncpg total_seconds)", () => {
  const secs = (s: string): number => {
    const v = pgIntervalSeconds(s);
    return v instanceof PyFloat ? v.value : NaN;
  };
  test("hh:mm:ss", () => {
    expect(secs("02:00:00")).toBe(7200);
    expect(secs("00:00:32.486489")).toBeCloseTo(32.486489, 6);
  });
  test("days", () => {
    expect(secs("1 day 02:00:00")).toBe(93600);
    expect(secs("2 days")).toBe(172800);
  });
  test("months count as 30 days", () => {
    expect(secs("1 mon")).toBe(2592000);
    expect(secs("1 year")).toBe(12 * 2592000);
  });
  test("negative time part", () => {
    expect(secs("-1 days +02:03:04")).toBe(-86400 + 7384);
  });
});

describe("numeric conversion (pydantic decimal_encoder)", () => {
  test("whole numbers become ints", () => {
    expect(pgNumericText("42")).toBe(42);
    expect(pyJson(pgNumericText("42"))).toBe("42");
  });
  test("fractional (even all-zero) become floats", () => {
    expect(pyJson(pgNumericText("0.000000"))).toBe("0.0");
    expect(pyJson(pgNumericText("12.3400"))).toBe("12.34");
  });
  test("NaN/Infinity become null", () => {
    expect(pgNumericText("NaN")).toBeNull();
    expect(pgNumericText("Infinity")).toBeNull();
  });
});

describe("convertRow", () => {
  test("applies per-column conversions in place", () => {
    const row: Record<string, unknown> = {
      d: new Date(Date.UTC(2007, 1, 28)),
      n: "1.5",
      f: 2,
      untouched: "1.5",
      missing: null,
    };
    convertRow(row, { d: "date", n: "num", f: "float" });
    expect(row.d).toBe("2007-02-28");
    expect(pyJson(row.n)).toBe("1.5");
    expect(pyJson(row.f)).toBe("2.0");
    expect(row.untouched).toBe("1.5");
    expect(row.missing).toBeNull();
  });
  test("date helper", () => {
    expect(pgDate(new Date(Date.UTC(2020, 11, 31)))).toBe("2020-12-31");
  });
});
