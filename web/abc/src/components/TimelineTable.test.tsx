import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TimelineEvent } from "../api/types";
import { TimelineTable } from "./TimelineTable";

function event(overrides: Partial<TimelineEvent>): TimelineEvent {
  return {
    inbox_content_id: 1,
    subprocess_invocation_id: 1,
    operation_name: "Op",
    user_name: "admin",
    started: "2026-08-27T02:48:29Z",
    ended: "2026-08-27T02:49:07Z",
    duration: "PT37.9S",
    command_line: "Op.pl 1",
    email_file_id: 10,
    spreadsheet_file_id: null,
    timepoint_id: null,
    timepoint_file_count: null,
    overlap_count: 0,
    ...overrides,
  };
}

describe("TimelineTable", () => {
  it("renders one row per event with timepoint and overlap columns", () => {
    const events = [
      event({ inbox_content_id: 2, subprocess_invocation_id: 7, timepoint_id: 3, timepoint_file_count: 718, overlap_count: 1 }),
      event({ inbox_content_id: 1, subprocess_invocation_id: 6, spreadsheet_file_id: 20 }),
    ];

    render(<TimelineTable events={events} activityId={1} onRefresh={() => {}} />);

    const rows = screen.getAllByRole("row").slice(1); // header row
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("7");
    expect(rows[0]).toHaveTextContent("718");
    expect(screen.getByLabelText("from timepoint 3")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "email" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "input" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Compare timepoints" })).toBeDisabled();
  });

  it("says so when there are no events", () => {
    render(<TimelineTable events={[]} activityId={1} onRefresh={() => {}} />);
    expect(screen.getByText(/No reports for this activity yet/)).toBeInTheDocument();
  });
});
