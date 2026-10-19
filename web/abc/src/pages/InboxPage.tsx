import { Link } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import type { InboxItem } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { formatTimestamp } from "../lib/format";

export function InboxPage() {
  const me = useMe();
  const { data, error } = useSWR<InboxItem[]>(paths.inbox(), { refreshInterval: 10000 });
  if (error) return <p className="text-red-700">{String(error)}</p>;
  if (!data) return <p className="text-gray-500">Loading…</p>;
  return (
    <div>
      <h1 className="text-xl font-semibold">Message Inbox for {me.username}</h1>
      <table className="table-grid mt-3 max-w-4xl">
        <thead>
          <tr>
            <th>Message ID</th>
            <th>Operation</th>
            <th>Status</th>
            <th>Created Date</th>
          </tr>
        </thead>
        <tbody>
          {data.length === 0 && (
            <tr>
              <td colSpan={4} className="text-gray-500">
                No messages.
              </td>
            </tr>
          )}
          {data.map((item) => (
            <tr key={item.user_inbox_content_id}>
              <td>
                <Link className="btn" to={`/inbox/${item.user_inbox_content_id}`}>
                  {item.user_inbox_content_id}
                </Link>
              </td>
              <td>{item.operation_name}</td>
              <td className={item.current_status === "entered" || item.current_status === "new" ? "font-semibold" : ""}>
                {item.current_status}
              </td>
              <td className="whitespace-nowrap">{formatTimestamp(item.date_entered)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
