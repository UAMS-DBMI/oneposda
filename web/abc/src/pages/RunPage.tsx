import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { paths, rerun, runAction, setBinding, setRunFilter } from "../api/abc";
import { ApiError, api } from "../api/client";
import {
  ACTIVE_RUN_STATES,
  type Candidates,
  type Cell,
  type ChainedQuery,
  type ColumnButton,
  type LaunchSource,
  type QueryDetail,
  type RowsPage,
  type RunDetail,
} from "../api/types";
import { CandidateOperationsTable } from "../components/CandidateOperationsTable";
import { LaunchDialog } from "../components/LaunchDialog";
import { Badge, EmptyState, ErrorMessage, Loading, Pagination, SegmentedControl, errorText, runStateTone } from "../components/ui";
import { formatTimestamp } from "../lib/format";
import { isViewerButton, viewerUrl } from "../lib/viewerLinks";

const LAUNCHER_OBJ = "Posda::NewerProcessPopup";

const DEFAULT_ROWS = 30;

function cellText(cell: Cell): string {
  if (cell === null) return "";
  if (Array.isArray(cell)) return "{" + cell.map(cellText).join(",") + "}";
  return String(cell);
}

/** Columns whose loaded values are all numbers (or null), for right alignment. */
function numericColumnSet(columns: string[], rows: Cell[][]): Set<string> {
  const numeric = new Set<string>();
  columns.forEach((column, index) => {
    const values = rows.map((row) => row[index]).filter((v) => v !== null && v !== undefined);
    if (values.length > 0 && values.every((v) => typeof v === "number")) numeric.add(column);
  });
  return numeric;
}

function stateLabel(state: string): string {
  switch (state) {
    case "done":
      return "Complete";
    case "running":
      return "Running";
    case "queued":
      return "Queued";
    case "paused":
      return "Paused";
    case "aborted":
      return "Aborted";
    case "ended":
      return "Ended early";
    case "lost":
      return "Lost (worker stopped reporting)";
    case "error":
      return "Failed";
    default:
      return state;
  }
}

/** One foreground query run: status, filter, paging, rows and controls. */
export function RunPage() {
  const params = useParams<{ runId: string }>();
  const runId = Number(params.runId);
  const navigate = useNavigate();
  const run = useSWR<RunDetail>(Number.isInteger(runId) ? paths.run(runId) : null, {
    refreshInterval: (data) => (data && ACTIVE_RUN_STATES.includes(data.state) ? 2000 : 0),
  });
  const query = useSWR<QueryDetail>(run.data ? paths.query(run.data.query_name) : null);
  const [first, setFirst] = useState(0);
  const [rowsToShow, setRowsToShow] = useState(DEFAULT_ROWS);
  const [viewFiltered, setViewFiltered] = useState<boolean | null>(null);
  const [editing, setEditing] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [launch, setLaunch] = useState<LaunchSource | null>(null);
  const [candidates, setCandidates] = useState<Candidates | null>(null);

  const filtered = viewFiltered ?? run.data?.view_filtered ?? false;
  const useFilter = filtered && !!run.data?.filter;
  const rows = useSWR<RowsPage>(
    run.data && run.data.is_select !== false
      ? paths.runRows(runId, first, rowsToShow, useFilter)
      : null,
    {
      refreshInterval: run.data && ACTIVE_RUN_STATES.includes(run.data.state) ? 2000 : 0,
      keepPreviousData: true,
    },
  );

  useEffect(() => setFirst(0), [useFilter]);

  if (!Number.isInteger(runId)) return <ErrorMessage>Bad run id.</ErrorMessage>;
  if (run.error instanceof ApiError && (run.error.status === 404 || run.error.status === 410)) {
    return (
      <ErrorMessage>
        {run.error.detail} <Link to="/queries?tab=active" className="link">All results</Link>
      </ErrorMessage>
    );
  }
  if (run.error) return <ErrorMessage error={run.error} />;
  if (!run.data) return <Loading />;
  const detail = run.data;
  const active = ACTIVE_RUN_STATES.includes(detail.state);
  const total = useFilter ? (detail.filtered_count ?? 0) : detail.row_count;
  const filterEntries = Object.entries(detail.filter ?? {}).filter(([, v]) => v !== "");

  async function act(action: "pause" | "resume" | "abort" | "dismiss") {
    setError(null);
    try {
      await runAction(runId, action);
      await run.mutate();
      if (action === "dismiss") navigate("/queries?tab=active");
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function again() {
    const id = await rerun(runId);
    navigate(`/runs/${id}`);
  }

  async function applyFilter(event?: FormEvent) {
    event?.preventDefault();
    if (editing === null) return;
    setError(null);
    try {
      await setRunFilter(runId, editing, true);
      setEditing(null);
      setViewFiltered(true);
      await run.mutate();
      await rows.mutate();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function clearFilter() {
    await setRunFilter(runId, null, false);
    setEditing(null);
    setViewFiltered(false);
    await run.mutate();
  }

  async function openChained(chain: ChainedQuery, row: Cell[]) {
    const byColumn = Object.fromEntries(detail.columns.map((c, i) => [c, row[i]]));
    for (const [fromColumn, toParam] of Object.entries(chain.arg_map)) {
      await setBinding(toParam, cellText(byColumn[fromColumn] ?? null));
    }
    navigate(`/queries/${encodeURIComponent(chain.to_query)}`);
  }

  const chains = query.data?.chained_queries ?? [];
  const viewerButtons = (query.data?.column_buttons ?? []).filter(isViewerButton);
  const viewerByColumn = new Map<string, ColumnButton>(viewerButtons.map((b) => [b.column, b]));
  const rowLaunchers = (query.data?.column_buttons ?? []).filter(
    (b) => b.obj === LAUNCHER_OBJ && b.operation,
  );
  const processingButtons = query.data?.processing_buttons ?? [];
  const numericColumns = numericColumnSet(detail.columns, rows.data?.rows ?? []);

  async function chainToOperation() {
    setError(null);
    try {
      setCandidates(await api.get<Candidates>(paths.candidatesForRun(runId, useFilter)));
    } catch (err) {
      setError(errorText(err));
    }
  }

  const viewOptions = [
    { value: "all", label: `All rows (${detail.row_count})` },
    {
      value: "filtered",
      label: `Filtered (${detail.filter ? (detail.filtered_count ?? "…") : "none"})`,
      title: detail.filter ? "Rows matching the filter" : "No filter is defined yet",
    },
  ] as const;

  return (
    <div>
      <p className="mb-1 text-sm">
        <Link to="/queries" className="link">Queries</Link>
        <span className="mx-1 text-slate-400">/</span>
        <Link to="/queries?tab=active" className="link">Results</Link>
        <span className="mx-1 text-slate-400">/</span>
        <span className="text-slate-600">run {runId}</span>
      </p>
      <div className="card mb-3 py-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="min-w-0 flex-1">
            <h1 className="truncate" title={detail.caption}>
              {detail.caption}
            </h1>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
              <Badge tone={runStateTone(detail.state)}>{stateLabel(detail.state)}</Badge>
              {detail.requested_action && <span className="text-amber-700">{detail.requested_action} requested…</span>}
              <span>started {formatTimestamp(detail.started_at ?? detail.created_at)}</span>
              {detail.is_select !== false && (
                <span className="tabular-nums">
                  {detail.row_count} rows{active ? " so far" : ""}
                </span>
              )}
              <Link to={`/queries/${encodeURIComponent(detail.query_name)}`} className="link" title="Open the argument form for this query">
                edit arguments
              </Link>
            </p>
          </div>
          <div className="toolbar">
            {detail.state === "running" && detail.requested_action !== "pause" && (
              <button type="button" className="btn" onClick={() => act("pause")}>Pause</button>
            )}
            {detail.state === "running" && detail.requested_action === "pause" && (
              <button type="button" className="btn" onClick={() => act("resume")}>Cancel pause</button>
            )}
            {detail.state === "paused" && (
              <button type="button" className="btn-primary" onClick={() => act("resume")}>Resume</button>
            )}
            {active && (
              <button type="button" className="btn-danger" onClick={() => act("abort")}>
                {detail.state === "paused" ? "End" : "Abort"}
              </button>
            )}
            {!active && (
              <button type="button" className="btn" onClick={again} title="Run the same query with the same arguments again">Re-run</button>
            )}
            {detail.is_select !== false && (
              <a className="btn" href={paths.runCsv(runId, useFilter)} title={useFilter ? "Download the filtered rows as CSV" : "Download all rows as CSV"}>
                Download CSV
              </a>
            )}
            {!active && (
              <button type="button" className="btn" onClick={() => act("dismiss")} title="Forget this result">Dismiss</button>
            )}
          </div>
        </div>
      </div>
      {detail.error_text && (
        <pre className="notice notice-danger mb-3 whitespace-pre-wrap font-mono text-xs">{detail.error_text}</pre>
      )}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {detail.is_select === false ? (
        <p className="card text-sm">
          {detail.state === "done"
            ? `The statement affected ${detail.rows_affected ?? 0} rows.`
            : `Statement ${stateLabel(detail.state).toLowerCase()}.`}
        </p>
      ) : (
        <>
          <div className="toolbar mb-2">
            <SegmentedControl
              label="Rows to show"
              options={viewOptions}
              value={useFilter ? "filtered" : "all"}
              onChange={(v) => {
                if (v === "filtered" && !detail.filter) setEditing({ ...(detail.filter ?? {}) });
                else setViewFiltered(v === "filtered");
              }}
            />
            {filterEntries.length > 0 && !editing && (
              <span className="flex flex-wrap items-center gap-1">
                {filterEntries.map(([k, v]) => (
                  <span key={k} className="badge badge-neutral font-normal" title={`${k} matches /${v}/i`}>
                    <span className="font-medium">{k}</span> ~ <code className="bg-transparent px-0">{v}</code>
                  </span>
                ))}
                <button type="button" className="btn-ghost btn-sm" onClick={clearFilter}>clear</button>
              </span>
            )}
            {editing ? (
              <>
                <button type="button" className="btn-primary btn-sm" onClick={() => applyFilter()}>Apply filter</button>
                <button type="button" className="btn btn-sm" onClick={() => setEditing(null)}>Cancel</button>
                <span className="text-xs text-slate-500">Type a pattern under each column; rows must match every one.</span>
              </>
            ) : (
              <button type="button" className="btn btn-sm" onClick={() => setEditing({ ...(detail.filter ?? {}) })}>
                {detail.filter ? "Edit filter" : "Filter rows…"}
              </button>
            )}
            {!active && (
              <span className="ml-auto flex flex-wrap items-center gap-1">
                <span className="text-xs text-slate-500">Send {useFilter ? "filtered" : "all"} rows to:</span>
                {processingButtons.map((button) => (
                  <button
                    key={button.operation}
                    type="button"
                    className="btn btn-sm"
                    title={button.operation}
                    onClick={() =>
                      setLaunch({
                        type: "table",
                        query_run_id: runId,
                        filtered: useFilter,
                        operation: button.operation,
                        caption: button.caption,
                      })
                    }
                  >
                    {button.caption}
                  </button>
                ))}
                <button type="button" className="btn btn-sm" onClick={chainToOperation} title="Pick any operation that takes these columns">
                  Any operation…
                </button>
              </span>
            )}
          </div>
          {candidates && (
            <div className="mb-3">
              <CandidateOperationsTable
                candidates={candidates.candidates}
                onChoose={(name) => {
                  setCandidates(null);
                  setLaunch({ type: "table", query_run_id: runId, filtered: useFilter, operation: name, caption: name });
                }}
              />
              <button type="button" className="btn btn-sm mt-1" onClick={() => setCandidates(null)}>Close</button>
            </div>
          )}
          <div className="mb-2">
            <Pagination
              first={first}
              pageSize={rowsToShow}
              total={total}
              partial={rows.data?.partial}
              onFirstChange={setFirst}
              onPageSizeChange={(n) => {
                setRowsToShow(n);
                setFirst(0);
              }}
            />
          </div>
          {rows.error && <ErrorMessage error={rows.error} />}
          <form onSubmit={applyFilter} className="table-wrap max-h-[calc(100vh-16rem)] overflow-auto">
            <table className="table-grid">
              <thead>
                <tr>
                  {chains.length > 0 && <th>chain</th>}
                  {rowLaunchers.length > 0 && <th>run</th>}
                  {detail.columns.map((c) => (
                    <th key={c} className={numericColumns.has(c) ? "num" : ""}>
                      {c}
                    </th>
                  ))}
                </tr>
                {editing && (
                  <tr>
                    {chains.length > 0 && <th className="top-7" />}
                    {rowLaunchers.length > 0 && <th className="top-7" />}
                    {detail.columns.map((column, i) => (
                      <th key={column} className="top-7 py-1">
                        <input
                          className="input w-full min-w-[6rem] py-0.5 font-normal"
                          value={editing[column] ?? ""}
                          onChange={(e) => setEditing({ ...editing, [column]: e.target.value })}
                          placeholder="regex"
                          aria-label={`filter ${column}`}
                          autoFocus={i === 0}
                        />
                      </th>
                    ))}
                  </tr>
                )}
              </thead>
              <tbody>
                {(rows.data?.rows ?? []).map((row, i) => {
                  const byColumn = Object.fromEntries(detail.columns.map((c, j) => [c, row[j]]));
                  return (
                    <tr key={first + i}>
                      {chains.length > 0 && (
                        <td className="space-x-1 whitespace-nowrap">
                          {chains.map((chain) => (
                            <button
                              key={chain.chained_query_id}
                              type="button"
                              className="btn btn-sm"
                              title={`Open ${chain.to_query} with this row's values`}
                              onClick={() => openChained(chain, row)}
                            >
                              {chain.caption}
                            </button>
                          ))}
                        </td>
                      )}
                      {rowLaunchers.length > 0 && (
                        <td className="space-x-1 whitespace-nowrap">
                          {rowLaunchers.map((button) => (
                            <button
                              key={button.button_id}
                              type="button"
                              className="btn btn-sm"
                              title={button.operation ?? ""}
                              onClick={() =>
                                setLaunch({
                                  type: "row",
                                  query_run_id: runId,
                                  filtered: useFilter,
                                  row_index: first + i,
                                  operation: button.operation ?? "",
                                  caption: button.caption,
                                })
                              }
                            >
                              {button.caption}
                            </button>
                          ))}
                        </td>
                      )}
                      {detail.columns.map((column, j) => {
                        const button = viewerByColumn.get(column);
                        const url = button ? viewerUrl(button, byColumn) : null;
                        const value = row[j] ?? null;
                        return (
                          <td key={column} className={numericColumns.has(column) ? "num" : ""}>
                            {cellText(value)}
                            {button && url && (
                              <a className="btn btn-sm ml-1" href={url} target="_blank" rel="noreferrer">
                                {button.caption}
                              </a>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {total === 0 && !active && <EmptyState>{useFilter ? "No rows match the filter." : "The query returned no rows."}</EmptyState>}
            {total === 0 && active && <Loading>Waiting for the first rows…</Loading>}
            <button type="submit" className="hidden" aria-hidden="true" tabIndex={-1} />
          </form>
        </>
      )}
      {launch && <LaunchDialog source={launch} onClose={() => setLaunch(null)} />}
    </div>
  );
}
