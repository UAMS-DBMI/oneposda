import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { paths, runQueryInBackground, startRun } from "../api/abc";
import { ApiError } from "../api/client";
import type { Bindings, Launched, QueryDetail, Timepoint } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { ErrorMessage, Loading, Notice, PageHeader, errorText } from "../components/ui";
import { useCurrentActivity } from "../hooks/useCurrentActivity";
import { hasFromTo, prefillArgs, quickDateRange, type QuickRange } from "../lib/queryArgs";

const QUICK: [QuickRange, string][] = [
  ["today", "Today"],
  ["yesterday", "Yesterday"],
  ["lastweek", "Last 7 days"],
  ["lastmonth", "Last 30 days"],
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
    return <ErrorMessage>There is no saved query named {name}.</ErrorMessage>;
  }
  if (query.error) return <ErrorMessage error={query.error} />;
  if (!query.data || values === null) return <Loading />;
  const detail = query.data;

  async function run(event?: FormEvent) {
    event?.preventDefault();
    if (!detail.runnable || busy) return;
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
      setError(errorText(err));
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
      setError(errorText(err));
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
    <form onSubmit={run} className="max-w-5xl">
      <p className="mb-1 text-sm">
        <Link to="/queries" className="link">Queries</Link>
        <span className="mx-1 text-slate-400">/</span>
        <span className="text-slate-600">{detail.name}</span>
      </p>
      <PageHeader
        title={detail.name}
        subtitle={
          <>
            <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs">{detail.schema_name}</span>
            {detail.is_select ? "select" : "modifies the database"}
          </>
        }
        actions={
          <>
            <button type="submit" className="btn-primary" disabled={busy || !detail.runnable}>
              Run
            </button>
            <button
              type="button"
              className="btn"
              onClick={runInBackground}
              disabled={busy || !detail.runnable}
              title="Run on a worker; the results arrive as a report in your inbox"
            >
              Run in background
            </button>
            <button type="button" className="btn" onClick={clear} disabled={detail.args.length === 0}>
              Clear
            </button>
          </>
        }
      />
      {!detail.runnable && <Notice tone="danger">Cannot run here: {detail.not_runnable_reason}</Notice>}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {queued && (
        <Notice tone="success" onDismiss={() => setQueued(null)}>
          Queued as worker item {queued.work_id} ({queued.pending_work} items in the worker queue). The results will
          arrive in your <Link to="/inbox" className="link">inbox</Link>.
        </Notice>
      )}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="card">
          <h2 className="card-title">Arguments</h2>
          {detail.args.length === 0 && <p className="text-sm text-slate-500">This query takes no arguments.</p>}
          <div className="grid gap-2">
            {detail.args.map((arg, i) => (
              <label key={arg} className="grid grid-cols-[12rem_minmax(0,1fr)] items-center gap-3 text-sm">
                <span className="truncate font-medium text-slate-700" title={arg}>{arg}</span>
                <input
                  className="input"
                  value={values[arg] ?? ""}
                  onChange={(e) => setValues({ ...values, [arg]: e.target.value })}
                  autoFocus={i === 0}
                />
              </label>
            ))}
            {hasFromTo(detail.args) && (
              <div className="grid grid-cols-[12rem_minmax(0,1fr)] items-center gap-3 text-sm">
                <span className="text-slate-500">quick ranges</span>
                <div className="flex flex-wrap gap-1">
                  {QUICK.map(([kind, label]) => (
                    <button key={kind} type="button" className="btn btn-sm" onClick={() => applyQuick(kind)}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          {detail.args.length > 0 && (
            <p className="mt-3 text-xs text-slate-500">
              Press <kbd className="kbd">Enter</kbd> to run. Values are remembered and pre-filled next time.
            </p>
          )}
        </section>
        <section className="card">
          <h2 className="card-title">Returns</h2>
          <p className="text-sm text-slate-700">{detail.columns.join(", ")}</p>
          {detail.description && (
            <>
              <h2 className="card-title mt-4">Description</h2>
              <p className="whitespace-pre-wrap text-sm text-slate-700">{detail.description}</p>
            </>
          )}
        </section>
      </div>
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-900">SQL</summary>
        <pre className="pre-block mt-2">{detail.query}</pre>
      </details>
    </form>
  );
}
