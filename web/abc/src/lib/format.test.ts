import { describe, expect, it } from "vitest";
import { formatDuration, formatTimestamp, parseIsoDuration } from "./format";

describe("parseIsoDuration", () => {
  it("handles the shapes pydantic emits", () => {
    expect(parseIsoDuration("PT37.888997S")).toBeCloseTo(37.888997);
    expect(parseIsoDuration("PT1M0.032924S")).toBeCloseTo(60.032924);
    expect(parseIsoDuration("PT2H")).toBe(7200);
    expect(parseIsoDuration("P1DT1S")).toBe(86401);
    expect(parseIsoDuration("-PT5S")).toBe(-5);
  });

  it("rejects other strings", () => {
    expect(() => parseIsoDuration("00:01:00")).toThrow();
  });
});

describe("formatDuration", () => {
  it("renders HH:MM:SS.ss like the Perl timeline", () => {
    expect(formatDuration("PT1M0.032924S")).toBe("00:01:00.03");
    expect(formatDuration("PT37.888997S")).toBe("00:00:37.89");
    expect(formatDuration("PT3H2M1S")).toBe("03:02:01.00");
    expect(formatDuration(null)).toBe("");
  });
});

describe("formatTimestamp", () => {
  it("formats a local date and time", () => {
    const date = new Date(2026, 7, 27, 2, 48, 29);
    expect(formatTimestamp(date.toISOString())).toBe("2026-08-27 02:48:29");
    expect(formatTimestamp(null)).toBe("");
    expect(formatTimestamp("garbage")).toBe("garbage");
  });
});
