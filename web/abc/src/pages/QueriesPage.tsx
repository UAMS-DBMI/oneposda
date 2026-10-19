import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import { ACTIVE_RUN_STATES, type QueryLists, type QuerySummary, type Run, type WorkflowGroup } from "../api/types";
import { ActiveRunsTable } from "../components/ActiveRunsTable";
import { QueryListTable } from "../components/QueryListTable";

type Tab = "active" | "recent" | "search" | "workflow";

const SEARCH_FIELDS: [keyof SearchState, string][] = [
  ["args", "Args containing"],
  ["columns", "Columns containing"],
  ["sql", "Query matching"],
  ["name", "Name matching"],
];

type SearchState = {
  args: string;
  columns: string;
  sql: string;
  name: string;
};

const EMPTY_SEARCH: SearchState = { args: "", columns: "", sql: "", name: "" };

export function QueriesPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab | null) ?? "recent";
  const navigate = useNavigate();
  const runs = useSWR<Run[]>(paths.runs(), {
    refreshInterval: (data) =>
      data?.some((r) => ACTIVE_RUN_STATES.includes(r.state)) ? 3000 : 0,
  });
  const activeCount = runs.data?.length ?? 0;

  function select(next: Tab) {
    setParams({ tab: next }, { replace: true });
  }

  const tabs: [Tab, string][] = [
    ...(activeCount > 0 ? ([["active", `active (${activeCount})`]] as [Tab, string][]) : []),
    ["recent", "recent"],
    ["search", "search"],
    ["workflow", "workflow"],
  ];

  return (
    <div>
      <h1 className="text-xl font-semibold">Queries</h1>
      <div className="my-3 flex gap-4 text-sm">
        {tabs.map(([key, label]) => (
          <label key={key} className="flex items-center gap-1">
            <input type="radio" name="tab" checked={tab === key} onChange={() => select(key)} />
            {label}
          </label>
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
  if (error) return <p className="text-red-700">{String(error)}</p>;
  if (!data) return <p className="text-gray-500">Loading…</p>;
  return (
    <>
      <QueryListTable caption="Most recent queries" queries={data.recent} emptyText="You have not run any queries yet." />
      <QueryListTable caption="Most frequent queries" queries={data.frequent} emptyText="Nothing else yet." />
    </>
  );
}

function SearchTab() {
  const [fields, setFields] = useState<SearchState>(EMPTY_SEARCH);
  const key = paths.queriesSearch(fields);
  const { data, error, isLoading } = useSWR<QuerySummary[]>(key);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        {SEARCH_FIELDS.map(([name, label]) => (
          <label key={name} className="text-sm">
            {label}:{" "}
            <input
              className="input"
              value={fields[name]}
              onChange={(e) => setFields({ ...fields, [name]: e.target.value })}
              placeholder="comma separated"
            />
          </label>
        ))}
        <button type="button" className="btn" onClick={() => setFields(EMPTY_SEARCH)}>
          clear
        </button>
      </div>
      {error && <p className="text-red-700">{String(error)}</p>}
      {key === null && <p className="text-sm text-gray-500">Enter a term above to search the saved queries.</p>}
      {key !== null && (
        <QueryListTable
          caption={isLoading ? "Searching…" : `Searched queries (${data?.length ?? 0} rows)`}
          queries={data ?? []}
          emptyText="No saved query matches."
        />
      )}
    </div>
  );
}

function WorkflowTab() {
  const { data, error } = useSWR<WorkflowGroup[]>(paths.workflowGroups);
  const [selected, setSelected] = useState("");
  if (error) return <p className="text-red-700">{String(error)}</p>;
  if (!data) return <p className="text-gray-500">Loading…</p>;
  const group = data.find((g) => g.name === selected);
  return (
    <div>
      <select className="input mb-3" value={selected} onChange={(e) => setSelected(e.target.value)}>
        <option value="">Select Workflow Group</option>
        {data.map((g) => (
          <option key={g.name} value={g.name}>
            {g.title}
          </option>
        ))}
      </select>
      {group && (
        <QueryListTable
          caption={group.title}
          queries={group.queries.flatMap((entry) => (entry.query ? [entry.query] : []))}
        />
      )}
      {group && group.queries.some((e) => !e.query) && (
        <p className="text-sm text-orange-700">
          Not defined in this database:{" "}
          {group.queries.filter((e) => !e.query).map((e) => e.query_name).join(", ")}
        </p>
      )}
    </div>
  );
}
