import { describe, expect, it } from "vitest";
import { describeTimeWindow, parseTimeWindow, TIME_WINDOWS } from "./timeWindow";

describe("parseTimeWindow", () => {
  it("accepts every preset", () => {
    for (const w of TIME_WINDOWS) expect(parseTimeWindow(w.value)).toBe(w.value);
  });
  it("falls back to 12 hours for unknown or missing values", () => {
    expect(parseTimeWindow(null)).toBe("12 hours");
    expect(parseTimeWindow("3 fortnights")).toBe("12 hours");
  });
});

describe("describeTimeWindow", () => {
  it("names the window or the lack of one", () => {
    expect(describeTimeWindow("6 hours")).toBe("in the last 6 hours");
    expect(describeTimeWindow("")).toBe("with no time limit");
  });
});
