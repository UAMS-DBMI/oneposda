import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import { ACTIVE_RUN_STATES, type QueryLists, type QuerySummary, type Run, type WorkflowGroup } from "../api/types";
import { ActiveRunsTable } from "../components/ActiveRunsTable";
import { QueryListTable } from "../components/QueryListTable";
import { ErrorMessage, Loading, PageHeader } from "../components/ui";

type Tab = "active" | "recent" | "search" | "workflow";

const SEARCH_FIELDS: [keyof SearchState, string, string][] = [
  ["name", "Name", "part of the query name"],
  ["args", "Argument", "an argument the query takes"],
  ["columns", "Column", "a column the query returns"],
  ["sql", "SQL", "text inside the query"],
];

type SearchState = {
  args: string;
  columns: string;
  sql: string;
  name: string;
};

const EMPTY_SEARCH: SearchState = { args: "", columns: "", sql: "", name: "" };

function parseTab(raw: string | null): Tab {
  return raw === "active" || raw === "search" || raw === "workflow" ? raw : "recent";
}

export function QueriesPage() {
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab"));
  const navigate = useNavigate();
  const runs = useSWR<Run[]>(paths.runs(), {
    refreshInterval: (data) =>
      data?.some((r) => ACTIVE_RUN_STATES.includes(r.state)) ? 3000 : 10000,
  });
  const runCount = runs.data?.length ?? 0;
  const runningCount = runs.data?.filter((r) => ACTIVE_RUN_STATES.includes(r.state)).length ?? 0;

  function select(next: Tab) {
    setParams({ tab: next }, { replace: true });
  }

  const tabs: { key: Tab; label: string; count?: number; live?: boolean }[] = [
    { key: "recent", label: "Recent" },
    { key: "search", label: "Search" },
    { key: "workflow", label: "Workflow groups" },
    { key: "active", label: "Results", count: runCount, live: runningCount > 0 },
  ];

  return (
    <div>
      <PageHeader title="Queries" subtitle="Run a saved query in the foreground to page through its rows, or in the background to get a report in your inbox." />
      <div className="tabs mb-4" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            className="tab"
            aria-selected={tab === t.key}
            onClick={() => select(t.key)}
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className={`badge ${t.live ? "badge-running" : "badge-neutral"} py-0`}>{t.count}</span>
            )}
          </button>
        ))}
      </div>
      {tab === "active" && (
        <ActiveRunsTable
          runs={runs.data ?? []}
          onChanged={() => runs.mutate()}
          onOpen={(id) => navigate(`/runs/${id}`)}
        />
      )}
      {tab === "recent" && <RecentTab />}
      {tab === "search" && <SearchTab />}
      {tab === "workflow" && <WorkflowTab />}
    </div>
  );
}

function RecentTab() {
  const { data, error } = useSWR<QueryLists>(paths.queriesRecent);
  if (error) return <ErrorMessage error={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <QueryListTable caption="Your most recent queries" queries={data.recent} emptyText="You have not run any queries yet." />
      <QueryListTable caption="Your most frequent queries" queries={data.frequent} emptyText="Nothing else yet." />
    </>
  );
}

/** Same value after the user has stopped typing for `delay` ms. */
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function SearchTab() {
  const [fields, setFields] = useState<SearchState>(EMPTY_SEARCH);
  const key = paths.queriesSearch(useDebounced(fields, 300));
  const { data, error, isLoading } = useSWR<QuerySummary[]>(key);
  const dirty = Object.values(fields).some((v) => v.trim() !== "");
  return (
    <div>
      <div className="card mb-4">
        <div className="flex flex-wrap items-end gap-3">
          {SEARCH_FIELDS.map(([name, label, hint], i) => (
            <label key={name} className="field">
              <span>{label}</span>
              <input
                className="input w-52"
                value={fields[name]}
                onChange={(e) => setFields({ ...fields, [name]: e.target.value })}
                placeholder={hint}
                autoFocus={i === 0}
              />
            </label>
          ))}
          <button type="button" className="btn" onClick={() => setFields(EMPTY_SEARCH)} disabled={!dirty}>
            Clear
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Matching is case-insensitive. Separate several terms with commas; every term must match.
        </p>
      </div>
      {error && <ErrorMessage error={error} />}
      {key !== null && (
        <QueryListTable
          caption={isLoading ? "Searching…" : `${data?.length ?? 0} matching queries`}
          queries={data ?? []}
          emptyText="No saved query matches."
        />
      )}
    </div>
  );
}

function WorkflowTab() {
  const [params, setParams] = useSearchParams();
  const { data, error } = useSWR<WorkflowGroup[]>(paths.workflowGroups);
  const selected = params.get("group") ?? "";
  const setSelected = (group: string) =>
    setParams(group ? { tab: "workflow", group } : { tab: "workflow" }, { replace: true });
  if (error) return <ErrorMessage error={error} />;
  if (!data) return <Loading />;
  const group = data.find((g) => g.name === selected);
  const missing = group?.queries.filter((e) => !e.query) ?? [];
  return (
    <div>
      <label className="field mb-4 max-w-md">
        <span>Workflow group</span>
        <select className="input" value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">Choose a group…</option>
          {data.map((g) => (
            <option key={g.name} value={g.name}>
              {g.title}
            </option>
          ))}
        </select>
      </label>
      {group && (
        <QueryListTable
          caption={group.title}
          queries={group.queries.flatMap((entry) => (entry.query ? [entry.query] : []))}
        />
      )}
      {missing.length > 0 && (
        <p className="notice notice-warning">
          Not defined in this database: {missing.map((e) => e.query_name).join(", ")}
        </p>
      )}
    </div>
  );
}
