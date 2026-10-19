/** Presets for "show things from the last …" controls, as Postgres intervals. */

export const TIME_WINDOWS = [
  { value: "1 hours", label: "1h", title: "Last hour" },
  { value: "6 hours", label: "6h", title: "Last 6 hours" },
  { value: "12 hours", label: "12h", title: "Last 12 hours" },
  { value: "24 hours", label: "24h", title: "Last 24 hours" },
  { value: "48 hours", label: "48h", title: "Last 48 hours" },
  { value: "", label: "All", title: "No time limit" },
] as const;

export type TimeWindow = (typeof TIME_WINDOWS)[number]["value"];

export const DEFAULT_TIME_WINDOW: TimeWindow = "12 hours";

/** The preset matching a stored/URL value, else the default. */
export function parseTimeWindow(raw: string | null | undefined): TimeWindow {
  if (raw === null || raw === undefined) return DEFAULT_TIME_WINDOW;
  const found = TIME_WINDOWS.find((w) => w.value === raw);
  return found ? found.value : DEFAULT_TIME_WINDOW;
}

/** Human text for a window, e.g. "in the last 12 hours" / "with no time limit". */
export function describeTimeWindow(value: TimeWindow): string {
  return value === "" ? "with no time limit" : `in the last ${value}`;
}
