import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import type { LaunchSource, Operation, WorkflowCategory } from "../api/types";
import { LaunchDialog } from "../components/LaunchDialog";
import { useCurrentActivity } from "../hooks/useCurrentActivity";

/** The Perl ActivityOperations page: one expandable step per category. */
export function WorkflowPage() {
  const navigate = useNavigate();
  const { activityId } = useCurrentActivity();
  const { data, error } = useSWR<WorkflowCategory[]>(paths.workflowCategories);
  const [open, setOpen] = useState<string>("1_associate");
  const [source, setSource] = useState<LaunchSource | null>(null);

  if (error) return <p className="text-red-700">{String(error)}</p>;
  if (!data) return <p className="text-gray-500">Loading…</p>;

  function launch(op: { action: string; caption: string; special: string | null }) {
    if (op.special === "spreadsheetRequest") {
      navigate(`/upload?operation=${encodeURIComponent(op.action)}`);
      return;
    }
    setSource({ type: "workflow", operation: op.action, caption: op.caption });
  }

  return (
    <div>
      <h1 className="text-xl font-semibold">Workflow</h1>
      {activityId === null && (
        <p className="my-2 text-sm text-orange-700">
          No activity is selected; activity_id will not be pre-filled.{" "}
          <Link to="/activities" className="text-blue-700">Choose one</Link>.
        </p>
      )}
      <div className="mt-3 max-w-4xl space-y-1">
        {data.map((category) => (
          <div key={category.id}>
            <button
              type="button"
              className="btn w-full justify-start text-base"
              onClick={() => setOpen(open === category.id ? "" : category.id)}
            >
              {category.name}
            </button>
            {open === category.id && (
              <blockquote className="ml-2 border-l-4 border-gray-300 py-2 pl-3 text-sm">
                <p>{category.description}</p>
                {category.note && (
                  <p className="mt-1">
                    <mark>Note: {category.note}</mark>
                  </p>
                )}
                {category.operations.length > 0 && (
                  <>
                    <p className="mt-2">Possible Operations:</p>
                    <ul className="ml-4 list-disc space-y-1">
                      {category.operations.map((op) => (
                        <li key={`${op.action}-${op.caption}`}>
                          <button
                            type="button"
                            className="btn"
                            disabled={!op.defined}
                            title={op.defined ? op.action : `${op.action} is not a defined operation`}
                            onClick={() => launch(op)}
                          >
                            {op.caption}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {category.query_groups.length > 0 && (
                  <>
                    <p className="mt-2">Possible Queries:</p>
                    <ul className="ml-4 list-disc space-y-1">
                      {category.query_groups.map((group) => (
                        <li key={group.query_list_name}>
                          <Link
                            className="btn"
                            to={`/queries?tab=workflow&group=${encodeURIComponent(group.query_list_name)}`}
                          >
                            {group.caption}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {category.operation_picker && <OperationPicker onLaunch={(name) => setSource({ type: "workflow", operation: name, caption: name })} />}
              </blockquote>
            )}
          </div>
        ))}
      </div>
      {source && <LaunchDialog source={source} onClose={() => setSource(null)} />}
    </div>
  );
}

function OperationPicker({ onLaunch }: { onLaunch: (name: string) => void }) {
  const { data } = useSWR<Operation[]>(paths.operations());
  const [name, setName] = useState("");
  const known = new Set((data ?? []).map((o) => o.operation_name));
  const trimmed = name.trim();
  return (
    <div className="mt-2">
      <p>Operation:</p>
      <input
        className="input w-96"
        list="operation_picker_list"
        placeholder="Type or choose an operation name"
        autoComplete="off"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <datalist id="operation_picker_list">
        {(data ?? []).map((o) => (
          <option key={o.operation_name} value={o.operation_name} />
        ))}
      </datalist>
      <button
        type="button"
        className="btn ml-2"
        disabled={!known.has(trimmed)}
        title={trimmed && !known.has(trimmed) ? `Unknown operation: ${trimmed}` : ""}
        onClick={() => onLaunch(trimmed)}
      >
        Launch Operation
      </button>
    </div>
  );
}
