import useSWR from "swr";
import { dismissTaskStatus, paths } from "../api/abc";
import type { TaskStatus } from "../api/types";

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

  if (error) return <p className="text-sm text-red-700">{String(error)}</p>;
  if (!data || data.length === 0) return null;

  return (
    <ul className="list-disc pl-5 text-sm">
      {data.map((status) => (
        <li key={status.subprocess_invocation_id}>
          {status.subprocess_invocation_id}: {status.operation_name} -{" "}
          {status.status_text}
          {status.stale_warning && (
            <span
              className="ml-1 font-semibold text-red-700"
              title="Nothing has updated this task recently; the process probably exited without closing it out."
            >
              [stalled: {status.stale_warning}]
            </span>
          )}{" "}
          <button
            type="button"
            className="btn"
            onClick={() => dismiss(status.subprocess_invocation_id)}
          >
            dismiss
          </button>
        </li>
      ))}
    </ul>
  );
}
