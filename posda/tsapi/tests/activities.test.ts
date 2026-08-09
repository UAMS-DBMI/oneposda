import { describe, expect, test } from "bun:test";
import { pydanticDatetime, pydanticDuration } from "../src/routes/activities";
import { parseSeriesSpec } from "../src/routes/series";
import { PyFloat } from "../src/pyjson";

// Expected values observed from the live pydantic v2 serialization.
describe("pydanticDuration", () => {
  const cases: [number, string][] = [
    [32.486489, "PT32.486489S"],
    [0.078987, "PT0.078987S"],
    [0, "PT0S"],
    [60, "PT1M"],
    [3600, "PT1H"],
    [86400, "P1D"],
    [90061.5, "P1DT1H1M1.5S"],
    [-3, "-PT3S"],
  ];
  for (const [seconds, want] of cases) {
    test(`${seconds}s -> ${want}`, () => {
      expect(pydanticDuration(new PyFloat(seconds))).toBe(want);
    });
  }
  test("non-interval values pass through", () => {
    expect(pydanticDuration(null)).toBeNull();
  });
});

describe("pydanticDatetime", () => {
  test("+00:00 becomes Z", () => {
    expect(pydanticDatetime("2026-08-04T21:04:38.100177+00:00")).toBe(
      "2026-08-04T21:04:38.100177Z",
    );
  });
  test("naive timestamps pass through", () => {
    expect(pydanticDatetime("2026-08-04T21:04:38")).toBe("2026-08-04T21:04:38");
  });
  test("null passes through", () => {
    expect(pydanticDatetime(null)).toBeNull();
  });
});

describe("parseSeriesSpec", () => {
  test("plain uid", () => {
    expect(parseSeriesSpec("1.2.3")).toEqual({
      uid: "1.2.3",
      activityId: null,
      timepointId: null,
    });
  });
  test("activity suffix", () => {
    expect(parseSeriesSpec("1.2.3@45")).toEqual({
      uid: "1.2.3",
      activityId: 45,
      timepointId: null,
    });
  });
  test("timepoint suffix", () => {
    expect(parseSeriesSpec("1.2.3:99")).toEqual({
      uid: "1.2.3",
      activityId: null,
      timepointId: 99,
    });
  });
  test("non-integer suffix is a 422", () => {
    expect(() => parseSeriesSpec("1.2.3@xx")).toThrow();
  });
});
