import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { paths, runQueryInBackground, startRun } from "../api/abc";
import { ApiError } from "../api/client";
import type { Bindings, Launched, QueryDetail, Timepoint } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { useCurrentActivity } from "../hooks/useCurrentActivity";
import { hasFromTo, prefillArgs, quickDateRange, type QuickRange } from "../lib/queryArgs";

const QUICK: [QuickRange, string][] = [
  ["today", "Today"],
  ["yesterday", "Yesterday"],
  ["lastweek", "Last 7 Days"],
  ["lastmonth", "Last 30 Days"],
];

/** The argument form for one saved query (Perl DrawNewQuery + MakeNewQuery). */
export function QueryPage() {
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const me = useMe();
  const { activityId } = useCurrentActivity();
  const query = useSWR<QueryDetail>(paths.query(name));
  const bindings = useSWR<Bindings>(paths.bindings);
  const timepoints = useSWR<Timepoint[]>(
    activityId !== null && query.data?.args.includes("activity_timepoint_id")
      ? paths.timepoints(activityId)
      : null,
  );
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [queued, setQueued] = useState<Launched | null>(null);

  const latestTimepointId = useMemo(() => {
    const ids = (timepoints.data ?? []).map((t) => t.activity_timepoint_id);
    return ids.length ? Math.max(...ids) : null;
  }, [timepoints.data]);

  const ready =
    query.data !== undefined &&
    bindings.data !== undefined &&
    (timepoints.data !== undefined || !query.data.args.includes("activity_timepoint_id") || activityId === null);

  useEffect(() => {
    if (values === null && ready && query.data && bindings.data) {
      setValues(
        prefillArgs(query.data.args, {
          activityId,
          latestTimepointId,
          username: me.username,
          bindings: bindings.data,
        }),
      );
    }
  }, [values, ready, query.data, bindings.data, activityId, latestTimepointId, me.username]);

  if (query.error instanceof ApiError && query.error.status === 404) {
    return <p className="text-red-700">There is no saved query named {name}.</p>;
  }
  if (query.error) return <p className="text-red-700">{String(query.error)}</p>;
  if (!query.data || values === null) return <p className="text-gray-500">Loading…</p>;
  const detail = query.data;

  async function run() {
    if (!detail.is_select) {
      const ok = window.confirm(
        `${detail.name} is not a select: it will modify the database. Run it?`,
      );
      if (!ok) return;
    }
    setBusy(true);
    setError(null);
    try {
      const id = await startRun(detail.name, values ?? {});
      await bindings.mutate();
      navigate(`/runs/${id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runInBackground() {
    setBusy(true);
    setError(null);
    try {
      setQueued(await runQueryInBackground(detail.name, values ?? {}, activityId));
      await bindings.mutate();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  function clear() {
    setValues(Object.fromEntries(detail.args.map((a) => [a, ""])));
  }

  function applyQuick(kind: QuickRange) {
    setValues({ ...(values ?? {}), ...quickDateRange(kind) });
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <button type="button" className="btn-primary" onClick={run} disabled={busy || !detail.runnable}>
          query
        </button>
        <button type="button" className="btn" onClick={runInBackground} disabled={busy || !detail.runnable} title="Run RunQueryInBackground.pl; the results arrive in your inbox">
          query in background
        </button>
        <button type="button" className="btn" onClick={clear}>
          clear
        </button>
        <Link to="/queries" className="ml-2 text-sm text-blue-700">
          back to queries
        </Link>
      </div>
      {!detail.runnable && (
        <p className="mb-2 text-sm text-red-700">Cannot run here: {detail.not_runnable_reason}</p>
      )}
      {error && <p className="mb-2 text-sm text-red-700">{error}</p>}
      {queued && (
        <p className="mb-2 rounded border border-green-300 bg-green-50 p-2 text-sm">
          Queued background query as worker {queued.work_id} ({queued.pending_work} items in the worker queue).
          The results will arrive in your <Link to="/inbox" className="text-blue-700">inbox</Link>.
        </p>
      )}
      <p className="text-sm">
        <strong>Query name:</strong> {detail.name}{" "}
        <span className="text-gray-500">({detail.schema_name})</span>
      </p>
      <p className="text-sm">
        <strong>Columns returned:</strong> {detail.columns.join(", ")}
      </p>
      {detail.description && (
        <p className="my-2 whitespace-pre-wrap text-sm text-gray-700">{detail.description}</p>
      )}
      <p className="mt-2 text-sm font-semibold">Arguments:</p>
      <table className="table-grid max-w-3xl">
        <tbody>
          {detail.args.map((arg) => (
            <tr key={arg}>
              <th className="w-48">{arg}</th>
              <td>
                <input
                  className="input w-full"
                  value={values[arg] ?? ""}
                  onChange={(e) => setValues({ ...values, [arg]: e.target.value })}
                />
              </td>
            </tr>
          ))}
          {hasFromTo(detail.args) && (
            <tr>
              <th>quick options</th>
              <td className="space-x-1">
                {QUICK.map(([kind, label]) => (
                  <button key={kind} type="button" className="btn" onClick={() => applyQuick(kind)}>
                    {label}
                  </button>
                ))}
              </td>
            </tr>
          )}
          {detail.args.length === 0 && (
            <tr>
              <td className="text-gray-500">This query takes no arguments.</td>
            </tr>
          )}
        </tbody>
      </table>
      <hr className="my-4" />
      <pre className="overflow-auto rounded bg-gray-50 p-3 font-mono text-xs">{detail.query}</pre>
    </div>
  );
}
