import { Link } from "react-router-dom";
import { runAction, rerun } from "../api/abc";
import { ACTIVE_RUN_STATES, type Run } from "../api/types";
import { formatTimestamp } from "../lib/format";
import { Badge, EmptyState, runStateTone } from "./ui";

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
  const finished = runs.filter((r) => !ACTIVE_RUN_STATES.includes(r.state));

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
    await Promise.all(finished.map((r) => runAction(r.query_run_id, "dismiss")));
    onChanged();
  }

  return (
    <div className="table-wrap">
      <table className="table-grid">
        <thead>
          <tr>
            <th className="num">id</th>
            <th>query</th>
            <th>started</th>
            <th>state</th>
            <th className="num">rows</th>
            <th className="text-right">
              <button type="button" className="btn btn-sm" onClick={dismissFinished} disabled={finished.length === 0}>
                Dismiss all finished
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const active = ACTIVE_RUN_STATES.includes(run.state);
            return (
              <tr key={run.query_run_id}>
                <td className="num">{run.query_run_id}</td>
                <td>
                  <Link className="link font-medium" to={`/runs/${run.query_run_id}`}>
                    {run.caption}
                  </Link>
                </td>
                <td className="whitespace-nowrap tabular-nums">{formatTimestamp(run.created_at)}</td>
                <td>
                  <Badge tone={runStateTone(run.state)}>{run.state}</Badge>
                  {run.requested_action && (
                    <span className="ml-1 text-xs text-slate-500">{run.requested_action} requested</span>
                  )}
                </td>
                <td className="num">{run.row_count}</td>
                <td className="space-x-1 whitespace-nowrap text-right">
                  <button type="button" className="btn btn-sm" onClick={() => onOpen(run.query_run_id)}>
                    Open
                  </button>
                  {run.state === "running" && run.requested_action !== "pause" && (
                    <button type="button" className="btn btn-sm" onClick={() => act(run, "pause")}>
                      Pause
                    </button>
                  )}
                  {run.state === "running" && run.requested_action === "pause" && (
                    <button type="button" className="btn btn-sm" onClick={() => act(run, "resume")}>
                      Cancel pause
                    </button>
                  )}
                  {run.state === "paused" && (
                    <button type="button" className="btn btn-sm" onClick={() => act(run, "resume")}>
                      Resume
                    </button>
                  )}
                  {active && (
                    <button type="button" className="btn-danger btn-sm" onClick={() => act(run, "abort")}>
                      {run.state === "paused" ? "End" : "Abort"}
                    </button>
                  )}
                  {run.state === "done" && (
                    <button type="button" className="btn btn-sm" onClick={() => again(run)}>
                      Re-run
                    </button>
                  )}
                  {!active && (
                    <button type="button" className="btn btn-sm" onClick={() => act(run, "dismiss")}>
                      Dismiss
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {runs.length === 0 && <EmptyState>No foreground queries. Results stay here until you dismiss them.</EmptyState>}
    </div>
  );
}
