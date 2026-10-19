import { Link } from "react-router-dom";
import { runAction, rerun } from "../api/abc";
import { ACTIVE_RUN_STATES, type Run } from "../api/types";
import { formatTimestamp } from "../lib/format";

/** Port of SelectFromCurrentForeground: one row per foreground query run. */
export function ActiveRunsTable({
  runs,
  onChanged,
  onOpen,
}: {
  runs: Run[];
  onChanged: () => void;
  onOpen: (runId: number) => void;
}) {
  async function act(run: Run, action: "pause" | "resume" | "abort" | "dismiss") {
    await runAction(run.query_run_id, action);
    onChanged();
  }

  async function again(run: Run) {
    const id = await rerun(run.query_run_id);
    onChanged();
    onOpen(id);
  }

  async function dismissFinished() {
    const finished = runs.filter((r) => !ACTIVE_RUN_STATES.includes(r.state));
    await Promise.all(finished.map((r) => runAction(r.query_run_id, "dismiss")));
    onChanged();
  }

  return (
    <table className="table-grid">
      <caption className="py-1 text-left text-sm font-semibold">
        Current Foreground Queries
      </caption>
      <thead>
        <tr>
          <th>id</th>
          <th>query</th>
          <th>when</th>
          <th>state</th>
          <th>rows</th>
          <th>
            <button type="button" className="btn" onClick={dismissFinished}>
              dismiss/delete all
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => {
          const active = ACTIVE_RUN_STATES.includes(run.state);
          return (
            <tr key={run.query_run_id}>
              <td>{run.query_run_id}</td>
              <td>
                <Link className="text-blue-700" to={`/runs/${run.query_run_id}`}>
                  {run.caption}
                </Link>
              </td>
              <td className="whitespace-nowrap">{formatTimestamp(run.created_at)}</td>
              <td>
                {run.state}
                {run.requested_action && (
                  <span className="text-gray-500"> ({run.requested_action} requested)</span>
                )}
              </td>
              <td>{run.row_count}</td>
              <td className="space-x-1 whitespace-nowrap">
                <button type="button" className="btn" onClick={() => onOpen(run.query_run_id)}>
                  select
                </button>
                {!active && (
                  <button type="button" className="btn" onClick={() => act(run, "dismiss")}>
                    dismiss
                  </button>
                )}
                {run.state === "running" && run.requested_action !== "pause" && (
                  <button type="button" className="btn" onClick={() => act(run, "pause")}>
                    pause
                  </button>
                )}
                {run.state === "running" && run.requested_action === "pause" && (
                  <button type="button" className="btn" onClick={() => act(run, "resume")}>
                    cancel pause
                  </button>
                )}
                {active && (
                  <button type="button" className="btn" onClick={() => act(run, "abort")}>
                    {run.state === "paused" ? "end" : "abort"}
                  </button>
                )}
                {run.state === "paused" && (
                  <button type="button" className="btn" onClick={() => act(run, "resume")}>
                    resume
                  </button>
                )}
                {run.state === "done" && (
                  <button type="button" className="btn" onClick={() => again(run)}>
                    re-run
                  </button>
                )}
              </td>
            </tr>
          );
        })}
        {runs.length === 0 && (
          <tr>
            <td colSpan={6} className="text-gray-500">
              No foreground queries.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
