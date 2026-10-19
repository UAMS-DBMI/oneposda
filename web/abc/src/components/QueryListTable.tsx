import { Link } from "react-router-dom";
import type { QuerySummary } from "../api/types";

/** The name / params / columns / make-query table the Perl lists used. */
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
    <table className="table-grid mb-4">
      <caption className="py-1 text-left text-sm font-semibold">{caption}</caption>
      <thead>
        <tr>
          <th>name</th>
          <th>params</th>
          <th>columns returned</th>
          <th>make query</th>
        </tr>
      </thead>
      <tbody>
        {queries.length === 0 && (
          <tr>
            <td colSpan={4} className="text-gray-500">
              {emptyText}
            </td>
          </tr>
        )}
        {queries.map((q) => (
          <tr key={q.name}>
            <td className="whitespace-nowrap">{q.name}</td>
            <td>{q.args.join(", ")}</td>
            <td>{q.columns.join(", ")}</td>
            <td className="whitespace-nowrap">
              <Link className="btn" to={`/queries/${encodeURIComponent(q.name)}`}>
                foreground
              </Link>{" "}
              <Link
                className="btn"
                to={`/queries/${encodeURIComponent(q.name)}?background=1`}
                title="Open the argument form and queue the query in the background"
              >
                background
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
