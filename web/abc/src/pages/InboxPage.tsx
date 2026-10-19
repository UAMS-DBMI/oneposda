import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import type { InboxItem } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { Badge, EmptyState, ErrorMessage, Loading, PageHeader, inboxStatusTone } from "../components/ui";
import { formatTimestamp } from "../lib/format";

function isUnread(item: InboxItem): boolean {
  return item.current_status === "entered" || item.current_status === "new";
}

export function InboxPage() {
  const me = useMe();
  const navigate = useNavigate();
  const [includeDismissed, setIncludeDismissed] = useState(false);
  const { data, error } = useSWR<InboxItem[]>(paths.inbox(includeDismissed), { refreshInterval: 10000 });
  const unread = data?.filter(isUnread).length ?? 0;
  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Inbox"
        subtitle={`Reports sent to ${me.username}${data ? ` · ${unread} unread` : ""}`}
        actions={
          <label className="flex items-center gap-1 text-slate-600">
            <input type="checkbox" checked={includeDismissed} onChange={(e) => setIncludeDismissed(e.target.checked)} />
            show dismissed
          </label>
        }
      />
      {error && <ErrorMessage error={error} />}
      {!data && !error && <Loading />}
      {data && (
        <div className="table-wrap">
          <table className="table-grid">
            <thead>
              <tr>
                <th className="num">message</th>
                <th>operation</th>
                <th>status</th>
                <th>received</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr
                  key={item.user_inbox_content_id}
                  className={`row-link ${isUnread(item) ? "font-semibold" : "text-slate-600"}`}
                  onClick={() => navigate(`/inbox/${item.user_inbox_content_id}`)}
                >
                  <td className="num">
                    <Link className="link" to={`/inbox/${item.user_inbox_content_id}`} onClick={(e) => e.stopPropagation()}>
                      {item.user_inbox_content_id}
                    </Link>
                  </td>
                  <td>{item.operation_name}</td>
                  <td>
                    <Badge tone={inboxStatusTone(item.current_status)}>{item.current_status ?? "unknown"}</Badge>
                  </td>
                  <td className="whitespace-nowrap tabular-nums">{formatTimestamp(item.date_entered)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.length === 0 && <EmptyState>No messages. Reports from background operations arrive here.</EmptyState>}
        </div>
      )}
    </div>
  );
}
