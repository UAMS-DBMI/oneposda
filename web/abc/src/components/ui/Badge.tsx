import type { ReactNode } from "react";

export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "running";

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

/** Tone for a query_run state. */
export function runStateTone(state: string): Tone {
  switch (state) {
    case "running":
    case "queued":
      return "running";
    case "paused":
      return "warning";
    case "done":
      return "success";
    case "ended":
      return "neutral";
    case "aborted":
    case "lost":
      return "warning";
    case "error":
      return "danger";
    default:
      return "neutral";
  }
}

/** Tone for a background job / work status. */
export function jobStatusTone(status: string | null): Tone {
  switch (status) {
    case "running":
      return "running";
    case "finished":
      return "success";
    case "errored":
      return "danger";
    case null:
      return "neutral";
    default:
      return "info";
  }
}

/** Tone for an inbox message status. */
export function inboxStatusTone(status: string): Tone {
  switch (status) {
    case "new":
    case "entered":
      return "info";
    case "dismissed":
      return "neutral";
    default:
      return "neutral";
  }
}
