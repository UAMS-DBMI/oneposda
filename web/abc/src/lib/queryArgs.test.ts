import { describe, expect, it } from "vitest";
import { hasFromTo, prefillArgs, quickDateRange } from "./queryArgs";

describe("prefillArgs", () => {
  it("applies the Perl precedence: activity, timepoint, notify, then bindings", () => {
    const values = prefillArgs(
      ["activity_id", "activity_timepoint_id", "notify", "collection", "other"],
      {
        activityId: 7,
        latestTimepointId: 12,
        username: "abc-dev",
        bindings: { activity_id: "99", collection: "LIDC", notify: "someone" },
      },
    );
    expect(values).toEqual({
      activity_id: "7",
      activity_timepoint_id: "12",
      notify: "abc-dev",
      collection: "LIDC",
      other: "",
    });
  });

  it("falls back to bindings when no activity is selected", () => {
    const values = prefillArgs(["activity_id", "activity_timepoint_id"], {
      activityId: null,
      latestTimepointId: null,
      username: "u",
      bindings: { activity_id: "3" },
    });
    expect(values).toEqual({ activity_id: "3", activity_timepoint_id: "" });
  });
});

describe("quickDateRange", () => {
  const now = new Date(2026, 2, 31, 15, 0, 0); // 31 March 2026, local

  it("matches the Perl quick options", () => {
    expect(quickDateRange("today", now)).toEqual({ from: "2026-03-31", to: "2026-04-01" });
    expect(quickDateRange("yesterday", now)).toEqual({ from: "2026-03-30", to: "2026-03-31" });
    expect(quickDateRange("lastweek", now)).toEqual({ from: "2026-03-24", to: "2026-04-01" });
    expect(quickDateRange("lastmonth", now).to).toBe("2026-04-01");
  });

  it("only shows the widget for a from followed by a to", () => {
    expect(hasFromTo(["from", "to"])).toBe(true);
    expect(hasFromTo(["to", "from"])).toBe(false);
    expect(hasFromTo(["from"])).toBe(false);
  });
});
