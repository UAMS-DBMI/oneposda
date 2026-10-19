/** Pre-filling a query's argument form, with the Perl DrawNewQuery rules. */

export interface PrefillContext {
  activityId: number | null;
  latestTimepointId: number | null;
  username: string;
  bindings: Record<string, string | null>;
}

/**
 * activity_id and activity_timepoint_id follow the selected activity, notify
 * is the user, anything else comes from the user's saved bindings, else blank.
 */
export function prefillArgs(args: string[], ctx: PrefillContext): Record<string, string> {
  const values: Record<string, string> = {};
  for (const arg of args) {
    if (arg === "activity_id" && ctx.activityId !== null) {
      values[arg] = String(ctx.activityId);
    } else if (arg === "activity_timepoint_id" && ctx.latestTimepointId !== null) {
      values[arg] = String(ctx.latestTimepointId);
    } else if (arg === "notify") {
      values[arg] = ctx.username;
    } else {
      values[arg] = ctx.bindings[arg] ?? "";
    }
  }
  return values;
}

export type QuickRange = "today" | "yesterday" | "lastweek" | "lastmonth";

function isoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function shifted(base: Date, days: number): Date {
  const copy = new Date(base);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function monthEarlier(base: Date): Date {
  const copy = new Date(base);
  copy.setMonth(copy.getMonth() - 1);
  return copy;
}

/** The from/to pair the Perl "quick options" buttons filled in (local dates). */
export function quickDateRange(kind: QuickRange, now = new Date()): { from: string; to: string } {
  const today = isoDate(now);
  const tomorrow = isoDate(shifted(now, 1));
  switch (kind) {
    case "today":
      return { from: today, to: tomorrow };
    case "yesterday":
      return { from: isoDate(shifted(now, -1)), to: today };
    case "lastweek":
      return { from: isoDate(shifted(now, -7)), to: tomorrow };
    case "lastmonth":
      return { from: isoDate(monthEarlier(now)), to: tomorrow };
  }
}

/** Whether the arg list has a "from" followed later by a "to". */
export function hasFromTo(args: string[]): boolean {
  const from = args.indexOf("from");
  return from >= 0 && args.indexOf("to") > from;
}
