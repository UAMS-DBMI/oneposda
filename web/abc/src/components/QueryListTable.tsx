import { Link } from "react-router-dom";
import type { QuerySummary } from "../api/types";
import { EmptyState } from "./ui";

/** The name / params / columns table the Perl lists used; the name opens the form. */
export function QueryListTable({
  caption,
  queries,
  emptyText = "No queries.",
}: {
  caption: string;
  queries: QuerySummary[];
  emptyText?: string;
}) {
  return (
    <div className="table-wrap mb-4">
      <table className="table-grid">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th>name</th>
            <th>arguments</th>
            <th>columns returned</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {queries.map((q) => (
            <tr key={q.name}>
              <td className="whitespace-nowrap font-medium">
                <Link className="link" to={`/queries/${encodeURIComponent(q.name)}`}>
                  {q.name}
                </Link>
              </td>
              <td className="text-slate-600">{q.args.join(", ")}</td>
              <td className="max-w-xl truncate text-slate-600" title={q.columns.join(", ")}>
                {q.columns.join(", ")}
              </td>
              <td className="whitespace-nowrap text-right">
                <Link className="btn btn-sm" to={`/queries/${encodeURIComponent(q.name)}`}>
                  Open
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {queries.length === 0 && <EmptyState>{emptyText}</EmptyState>}
    </div>
  );
}
