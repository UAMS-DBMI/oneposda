import useSWR from "swr";
import { dismissTaskStatus, paths } from "../api/abc";
import type { TaskStatus } from "../api/types";
import { Badge, ErrorMessage } from "./ui";

const REFRESH_MS = 3000;

/** Running/finished operation status lines for the activity, refreshed every 3 s. */
export function TaskStatusPanel({ activityId }: { activityId: number }) {
  const { data, error, mutate } = useSWR<TaskStatus[]>(paths.taskStatus(activityId), {
    refreshInterval: REFRESH_MS,
  });

  async function dismiss(subprocessInvocationId: number) {
    await dismissTaskStatus(activityId, subprocessInvocationId);
    await mutate();
  }

  async function dismissAll() {
    await Promise.all((data ?? []).map((s) => dismissTaskStatus(activityId, s.subprocess_invocation_id)));
    await mutate();
  }

  const tasks = data ?? [];
  return (
    <section className="card">
      <h2 className="card-title flex items-center gap-2">
        Tasks
        {tasks.length > 0 && <Badge tone="running">{tasks.length} open</Badge>}
        {tasks.length > 1 && (
          <button type="button" className="btn-ghost btn-sm ml-auto" onClick={dismissAll} title="Hide every task status">
            dismiss all
          </button>
        )}
      </h2>
      {error && <ErrorMessage error={error} />}
      {tasks.length === 0 && !error && (
        <p className="text-sm text-slate-500">Nothing is running for this activity. Launches from Workflow and query results show up here.</p>
      )}
      <ul className="divide-y divide-slate-100 text-sm">
        {tasks.map((status) => (
          <li key={status.subprocess_invocation_id} className="flex items-start gap-2 py-1.5">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2">
                <span className="font-medium">{status.operation_name ?? "operation"}</span>
                <span className="text-xs text-slate-400">#{status.subprocess_invocation_id}</span>
                {status.stale_warning && (
                  <Badge tone="danger" title="Nothing has updated this task recently; the process probably exited without closing it out.">
                    stalled {status.stale_warning}
                  </Badge>
                )}
              </div>
              <div className="text-slate-600">{status.status_text}</div>
            </div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => dismiss(status.subprocess_invocation_id)}
              title="Hide this task status"
            >
              dismiss
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
