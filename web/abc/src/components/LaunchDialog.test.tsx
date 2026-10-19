import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LaunchPreview, Launched } from "../api/types";
import { LaunchDialog } from "./LaunchDialog";

const preview: LaunchPreview = {
  operation: {
    operation_name: "AddFilesToTimepoint",
    command_line: 'AddFilesToTimepoint.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>',
    operation_type: "background_process",
    input_line_format: "<file_id>",
    tags: [],
    can_chain: false,
    outdated: true,
    worker_priority: 0,
    args: ["activity_id", "comment", "notify"],
    meta_args: ["bkgrnd_id"],
    fields: ["file_id"],
    program: "AddFilesToTimepoint.pl",
    program_found: true,
  },
  button_name: "Add Files",
  args: {
    activity_id: { value: "1", source: "from current_settings" },
    comment: { value: "", source: "not present" },
    notify: { value: "abc-dev", source: "from current_settings" },
  },
  expanded_command: 'AddFilesToTimepoint.pl <?bkgrnd_id?> 1 "" abc-dev',
  input_line_count: 2,
  input_head: ["10", "11"],
  input_tail: [],
  spreadsheet_file_id: null,
  query_invoked_by_dbif_id: null,
};

const launched: Launched = {
  subprocess_invocation_id: 30,
  work_id: 16,
  queue_name: "work_queue_0",
  pending_work: 1,
  command_line: 'AddFilesToTimepoint.pl <?bkgrnd_id?> 1 "hi" abc-dev',
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("LaunchDialog", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("previews, lets the user edit an argument, and launches with the edits", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
        calls.push({ url, body });
        if (url.endsWith("/prepare")) return json(preview);
        if (url.endsWith("/launch")) return json(launched);
        throw new Error(`unexpected ${url}`);
      }),
    );
    const onClose = vi.fn();

    render(
      <LaunchDialog
        source={{ type: "workflow", operation: "AddFilesToTimepoint", caption: "Add Files" }}
        onClose={onClose}
      />,
    );

    expect(await screen.findByText(/This operation is outdated/)).toBeInTheDocument();
    expect(screen.getAllByText("from current_settings")).toHaveLength(2);
    expect(screen.getByText("2 lines to supply as input:")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("comment"), { target: { value: "hi" } });
    expect(screen.getByText('AddFilesToTimepoint.pl <?bkgrnd_id?> 1 "hi" abc-dev')).toBeInTheDocument();
    expect(screen.getByText("entered")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByText(/Successfully queued background process with worker 16/)).toBeInTheDocument();

    const launch = calls.find((c) => c.url.endsWith("/launch"));
    expect(launch?.body).toEqual({
      source: { type: "workflow", operation: "AddFilesToTimepoint", caption: "Add Files" },
      args: { activity_id: "1", comment: "hi", notify: "abc-dev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("disables Start when the program is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ ...preview, operation: { ...preview.operation, program_found: false } })),
    );
    render(<LaunchDialog source={{ type: "workflow", operation: "X" }} onClose={() => {}} />);
    expect(await screen.findByText(/Program not found/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  });
});
