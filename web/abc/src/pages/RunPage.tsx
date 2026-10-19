import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { paths, rerun, runAction, setBinding, setRunFilter } from "../api/abc";
import { api } from "../api/client";
import { ApiError } from "../api/client";
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
import { formatTimestamp } from "../lib/format";
import { isViewerButton, viewerUrl } from "../lib/viewerLinks";

const LAUNCHER_OBJ = "Posda::NewerProcessPopup";

const DEFAULT_ROWS = 30;

function cellText(cell: Cell): string {
  if (cell === null) return "";
  if (Array.isArray(cell)) return "{" + cell.map(cellText).join(",") + "}";
  return String(cell);
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
    { refreshInterval: run.data && ACTIVE_RUN_STATES.includes(run.data.state) ? 2000 : 0 },
  );

  useEffect(() => setFirst(0), [useFilter]);

  if (!Number.isInteger(runId)) return <p>Bad run id.</p>;
  if (run.error instanceof ApiError && (run.error.status === 404 || run.error.status === 410)) {
    return (
      <p className="text-red-700">
        {run.error.detail} <Link to="/queries?tab=active" className="text-blue-700">All queries</Link>
      </p>
    );
  }
  if (run.error) return <p className="text-red-700">{String(run.error)}</p>;
  if (!run.data) return <p className="text-gray-500">Loading…</p>;
  const detail = run.data;
  const active = ACTIVE_RUN_STATES.includes(detail.state);
  const total = useFilter ? (detail.filtered_count ?? 0) : detail.row_count;

  async function act(action: "pause" | "resume" | "abort" | "dismiss") {
    setError(null);
    try {
      await runAction(runId, action);
      await run.mutate();
      if (action === "dismiss") navigate("/queries?tab=active");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  async function again() {
    const id = await rerun(runId);
    navigate(`/runs/${id}`);
  }

  async function applyFilter() {
    if (editing === null) return;
    setError(null);
    try {
      await setRunFilter(runId, editing, true);
      setEditing(null);
      setViewFiltered(true);
      await run.mutate();
      await rows.mutate();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  async function clearFilter() {
    await setRunFilter(runId, null, false);
    setEditing(null);
    setViewFiltered(false);
    await run.mutate();
  }

  function page(delta: number) {
    let next = first + delta;
    if (next + rowsToShow > total) next = total - rowsToShow;
    if (next < 0) next = 0;
    setFirst(next);
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

  async function chainToOperation() {
    setError(null);
    try {
      setCandidates(await api.get<Candidates>(paths.candidatesForRun(runId, useFilter)));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <span>
          <em>
            <b>{detail.state === "done" ? "Full" : `Partial (${detail.state})`} Results for:</b>
          </em>{" "}
          {detail.caption}
        </span>
        <span className="text-gray-500">started {formatTimestamp(detail.started_at ?? detail.created_at)}</span>
        {detail.requested_action && <span className="text-gray-500">({detail.requested_action} requested)</span>}
        <span className="ml-auto space-x-1">
          {detail.state === "running" && detail.requested_action !== "pause" && (
            <button type="button" className="btn" onClick={() => act("pause")}>pause</button>
          )}
          {detail.state === "running" && detail.requested_action === "pause" && (
            <button type="button" className="btn" onClick={() => act("resume")}>cancel pause</button>
          )}
          {detail.state === "paused" && (
            <button type="button" className="btn" onClick={() => act("resume")}>resume</button>
          )}
          {active && (
            <button type="button" className="btn" onClick={() => act("abort")}>
              {detail.state === "paused" ? "end" : "abort"}
            </button>
          )}
          {!active && (
            <button type="button" className="btn" onClick={again}>re-run</button>
          )}
          {!active && (
            <button type="button" className="btn" onClick={() => act("dismiss")}>dismiss</button>
          )}
          <Link to="/queries?tab=active" className="btn">all queries</Link>
        </span>
      </div>
      {detail.error_text && (
        <pre className="mb-2 whitespace-pre-wrap rounded border border-red-300 bg-red-50 p-2 text-xs text-red-800">{detail.error_text}</pre>
      )}
      {error && <p className="mb-2 text-sm text-red-700">{error}</p>}
      {detail.is_select === false ? (
        <p className="text-sm">
          {detail.state === "done"
            ? `Query affected ${detail.rows_affected ?? 0} rows.`
            : `Query ${detail.state}.`}
        </p>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-1">
              <input type="radio" checked={!filtered} onChange={() => setViewFiltered(false)} />
              Unfiltered rows: {detail.row_count}
            </label>
            <label className="flex items-center gap-1">
              <input type="radio" checked={filtered} onChange={() => setViewFiltered(true)} disabled={!detail.filter} />
              Filtered rows: {detail.filter ? (detail.filtered_count ?? "…") : "–"}
            </label>
            <span>
              {detail.filter ? (
                <>
                  Query Filter:{" "}
                  {Object.entries(detail.filter).map(([k, v]) => (
                    <code key={k} className="mr-2">{k} contains "{v}"</code>
                  ))}
                  <button type="button" className="btn ml-1" onClick={clearFilter}>clear</button>
                </>
              ) : (
                <span className="text-gray-500">No filter currently defined</span>
              )}
              <button
                type="button"
                className="btn ml-1"
                onClick={() => setEditing(editing ?? { ...(detail.filter ?? {}) })}
              >
                edit filter
              </button>
            </span>
            <a className="btn" href={paths.runCsv(runId, useFilter)}>download csv</a>
          </div>
          {!active && (
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
              {processingButtons.map((button) => (
                <button
                  key={button.operation}
                  type="button"
                  className="btn"
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
              <button type="button" className="btn" onClick={chainToOperation} title="Pick any operation that takes these columns">
                Chain
              </button>
            </div>
          )}
          {candidates && (
            <div className="mb-3">
              <CandidateOperationsTable
                candidates={candidates.candidates}
                onChoose={(name) => {
                  setCandidates(null);
                  setLaunch({ type: "table", query_run_id: runId, filtered: useFilter, operation: name, caption: name });
                }}
              />
              <button type="button" className="btn mt-1" onClick={() => setCandidates(null)}>close</button>
            </div>
          )}
          {editing && (
            <div className="mb-2 flex flex-wrap items-end gap-2 rounded border border-gray-300 p-2 text-sm">
              {detail.columns.map((column) => (
                <label key={column} className="flex flex-col">
                  {column}
                  <input
                    className="input"
                    value={editing[column] ?? ""}
                    onChange={(e) => setEditing({ ...editing, [column]: e.target.value })}
                    placeholder="regex"
                  />
                </label>
              ))}
              <button type="button" className="btn-primary" onClick={applyFilter}>apply</button>
              <button type="button" className="btn" onClick={() => setEditing(null)}>cancel</button>
            </div>
          )}
          <div className="mb-2 flex items-center gap-2 text-sm">
            First row:{" "}
            <input
              className="input w-20"
              value={first}
              onChange={(e) => setFirst(Math.max(0, Number(e.target.value) || 0))}
            />
            Show:{" "}
            <input
              className="input w-20"
              value={rowsToShow}
              onChange={(e) => setRowsToShow(Math.min(1000, Math.max(1, Number(e.target.value) || 1)))}
            />
            <button type="button" className="btn-primary" onClick={() => page(-rowsToShow)}>pg-up</button>
            <button type="button" className="btn-primary" onClick={() => page(rowsToShow)}>pg-dn</button>
            <span className="text-gray-500">
              {total === 0 ? "no rows" : `rows ${first + 1}–${Math.min(first + rowsToShow, total)} of ${total}`}
              {rows.data?.partial && " (more arriving)"}
            </span>
          </div>
          {rows.error && <p className="text-red-700">{String(rows.error)}</p>}
          <div className="overflow-x-auto">
            <table className="table-grid">
              <thead>
                <tr>
                  {chains.length > 0 && <th>chain</th>}
                  {rowLaunchers.length > 0 && <th>run</th>}
                  {detail.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
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
                              className="btn"
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
                              className="btn"
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
                        return (
                          <td key={column}>
                            {cellText(row[j] ?? null)}
                            {button && url && (
                              <a className="btn ml-1" href={url} target="_blank" rel="noreferrer">
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
          </div>
        </>
      )}
      {launch && <LaunchDialog source={launch} onClose={() => setLaunch(null)} />}
    </div>
  );
}
