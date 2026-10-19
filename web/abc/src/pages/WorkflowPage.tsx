import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import type { LaunchSource, Operation, WorkflowCategory } from "../api/types";
import { LaunchDialog } from "../components/LaunchDialog";
import { ErrorMessage, Loading, Notice, PageHeader } from "../components/ui";
import { useCurrentActivity } from "../hooks/useCurrentActivity";

/** The Perl ActivityOperations page: numbered steps, one open at a time. */
export function WorkflowPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { activityId } = useCurrentActivity();
  const { data, error } = useSWR<WorkflowCategory[]>(paths.workflowCategories);
  const [source, setSource] = useState<LaunchSource | null>(null);

  if (error) return <ErrorMessage error={error} />;
  if (!data) return <Loading />;

  const openId = params.get("step") ?? data[0]?.id ?? "";
  const open = data.find((c) => c.id === openId) ?? data[0];
  const openIndex = data.findIndex((c) => c.id === open?.id);

  function show(id: string) {
    setParams({ step: id }, { replace: true });
  }

  function launch(op: { action: string; caption: string; special: string | null }) {
    if (op.special === "spreadsheetRequest") {
      navigate(`/upload?operation=${encodeURIComponent(op.action)}`);
      return;
    }
    setSource({ type: "workflow", operation: op.action, caption: op.caption });
  }

  return (
    <div>
      <PageHeader title="Workflow" subtitle="The curation steps in order. Open a step to see the operations and queries that belong to it." />
      {activityId === null && (
        <Notice tone="warning">
          No activity is selected, so activity_id will not be pre-filled.{" "}
          <Link to="/activities" className="link">Choose one</Link>.
        </Notice>
      )}
      <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <ol className="card divide-y divide-slate-100 p-0" aria-label="Steps">
          {data.map((category, i) => {
            const active = category.id === open?.id;
            return (
              <li key={category.id}>
                <button
                  type="button"
                  className={`flex w-full items-start gap-3 px-3 py-2 text-left text-sm transition-colors ${
                    active ? "bg-blue-50 text-blue-900" : "hover:bg-slate-50"
                  }`}
                  aria-current={active ? "step" : undefined}
                  onClick={() => show(category.id)}
                >
                  <span
                    className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                      active ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-700"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-medium">{stepTitle(category.name)}</span>
                    <span className="block text-xs text-slate-500">
                      {category.operations.length > 0 && `${category.operations.length} operations`}
                      {category.operations.length > 0 && category.query_groups.length > 0 && " · "}
                      {category.query_groups.length > 0 && `${category.query_groups.length} query groups`}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        {open && (
          <section className="card">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Step {openIndex + 1}</p>
                <h2 className="text-lg">{stepTitle(open.name)}</h2>
              </div>
              <div className="toolbar">
                <button type="button" className="btn btn-sm" disabled={openIndex <= 0} onClick={() => show(data[openIndex - 1].id)}>
                  ‹ Previous
                </button>
                <button type="button" className="btn btn-sm" disabled={openIndex >= data.length - 1} onClick={() => show(data[openIndex + 1].id)}>
                  Next ›
                </button>
              </div>
            </div>
            <p className="text-sm text-slate-700">{open.description}</p>
            {open.note && <Notice tone="warning">{open.note}</Notice>}
            {open.operations.length > 0 && (
              <>
                <h3 className="mb-2 mt-4">Operations</h3>
                <div className="flex flex-wrap gap-2">
                  {open.operations.map((op) => (
                    <button
                      key={`${op.action}-${op.caption}`}
                      type="button"
                      className="btn"
                      disabled={!op.defined}
                      title={op.defined ? `Launch ${op.action}` : `${op.action} is not a defined operation`}
                      onClick={() => launch(op)}
                    >
                      {op.caption}
                      {op.special === "spreadsheetRequest" && <span className="text-xs text-slate-400">(needs a spreadsheet)</span>}
                    </button>
                  ))}
                </div>
              </>
            )}
            {open.query_groups.length > 0 && (
              <>
                <h3 className="mb-2 mt-4">Queries</h3>
                <div className="flex flex-wrap gap-2">
                  {open.query_groups.map((group) => (
                    <Link
                      key={group.query_list_name}
                      className="btn"
                      to={`/queries?tab=workflow&group=${encodeURIComponent(group.query_list_name)}`}
                    >
                      {group.caption}
                    </Link>
                  ))}
                </div>
              </>
            )}
            {open.operation_picker && (
              <OperationPicker onLaunch={(name) => setSource({ type: "workflow", operation: name, caption: name })} />
            )}
          </section>
        )}
      </div>
      {source && <LaunchDialog source={source} onClose={() => setSource(null)} />}
    </div>
  );
}

/** "1. Associate files" → "Associate files": the list already numbers the steps. */
function stepTitle(name: string): string {
  return name.replace(/^\s*\d+[.)]?\s*/, "");
}

function OperationPicker({ onLaunch }: { onLaunch: (name: string) => void }) {
  const { data } = useSWR<Operation[]>(paths.operations());
  const [name, setName] = useState("");
  const known = new Set((data ?? []).map((o) => o.operation_name));
  const trimmed = name.trim();
  return (
    <div className="mt-4">
      <h3 className="mb-2">Any operation</h3>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="input w-96 max-w-full"
          list="operation_picker_list"
          placeholder="Type or choose an operation name"
          autoComplete="off"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && known.has(trimmed)) onLaunch(trimmed);
          }}
        />
        <datalist id="operation_picker_list">
          {(data ?? []).map((o) => (
            <option key={o.operation_name} value={o.operation_name} />
          ))}
        </datalist>
        <button
          type="button"
          className="btn-primary"
          disabled={!known.has(trimmed)}
          title={trimmed && !known.has(trimmed) ? `Unknown operation: ${trimmed}` : ""}
          onClick={() => onLaunch(trimmed)}
        >
          Launch
        </button>
      </div>
    </div>
  );
}
