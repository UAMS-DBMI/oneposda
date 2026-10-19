import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR, { useSWRConfig } from "swr";
import { dismissInboxItem, fileInboxItem, forwardInboxItem, paths } from "../api/abc";
import { ApiError } from "../api/client";
import type { InboxItemDetail } from "../api/types";
import { useCurrentActivity } from "../hooks/useCurrentActivity";
import { formatTimestamp } from "../lib/format";

const URL_PATTERN = /(https?:\/\/[^\s<>"]+)/g;

/** Report text with http(s) URLs turned into links, as the Perl page did. */
export function Linkified({ text }: { text: string }) {
  const parts = text.split(URL_PATTERN);
  return (
    <>
      {parts.map((part, i) =>
        /^https?:\/\//.test(part) ? (
          <a key={i} href={part} className="text-blue-700 underline" target="_blank" rel="noreferrer">
            {part}
          </a>
        ) : (
          part
        ),
      )}
    </>
  );
}

export function InboxItemPage() {
  const { itemId = "" } = useParams<{ itemId: string }>();
  const id = Number(itemId);
  const navigate = useNavigate();
  const { mutate: mutateGlobal } = useSWRConfig();
  const { activityId } = useCurrentActivity();
  const { data, error, mutate } = useSWR<InboxItemDetail>(Number.isInteger(id) ? paths.inboxItem(id) : null);
  const users = useSWR<string[]>(paths.inboxUsers);
  const [forwardTo, setForwardTo] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  if (error instanceof ApiError && error.status === 404) return <p className="text-red-700">No inbox item {itemId}.</p>;
  if (error) return <p className="text-red-700">{String(error)}</p>;
  if (!data) return <p className="text-gray-500">Loading…</p>;

  async function run(action: () => Promise<void>, done: string, back = false) {
    setFailure(null);
    try {
      await action();
      setMessage(done);
      await mutate();
      await mutateGlobal(paths.inboxUnread);
      await mutateGlobal(paths.inbox());
      if (back) navigate("/inbox");
    } catch (err) {
      setFailure(err instanceof ApiError ? err.detail : String(err));
    }
  }

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/inbox" className="text-blue-700">Inbox</Link> / message {id}
        {data.operation_name && <span className="text-gray-600"> ({data.operation_name})</span>}
      </p>
      <table className="table-grid max-w-2xl">
        <thead>
          <tr>
            <th>Status</th>
            <th>Date Entered</th>
            <th>Date Dismissed</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{data.current_status}</td>
            <td>{formatTimestamp(data.date_entered)}</td>
            <td>{formatTimestamp(data.date_dismissed)}</td>
          </tr>
        </tbody>
      </table>
      <pre className="my-3 max-h-[60vh] overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 font-mono text-xs">
        {data.text !== null ? <Linkified text={data.text} /> : "(no report text)"}
        {data.text_truncated && "\n… (truncated)"}
      </pre>
      {data.file_id !== null && (
        <p className="mb-2 text-sm">
          <a className="text-blue-700" href={paths.fileData(data.file_id)} target="_blank" rel="noreferrer">
            download report (file {data.file_id})
          </a>
        </p>
      )}
      {message && <p className="mb-2 text-sm text-green-800">{message}</p>}
      {failure && <p className="mb-2 text-sm text-red-700">{failure}</p>}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {data.date_dismissed === null && (
          <button type="button" className="btn" onClick={() => run(() => dismissInboxItem(id), "Dismissed.", true)}>
            Dismiss this message
          </button>
        )}
        {forwardTo === null ? (
          <button type="button" className="btn" onClick={() => setForwardTo(users.data?.[0] ?? "")}>
            Forward this message
          </button>
        ) : (
          <span className="flex items-center gap-1 rounded border border-blue-300 bg-blue-50 p-1">
            Forward this message to:
            <select className="input" value={forwardTo} onChange={(e) => setForwardTo(e.target.value)}>
              {(users.data ?? []).map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
            <button
              type="button"
              className="btn-primary"
              disabled={!forwardTo}
              onClick={() => run(() => forwardInboxItem(id, forwardTo), `Forwarded to ${forwardTo}.`).then(() => setForwardTo(null))}
            >
              Do it
            </button>
            <button type="button" className="btn" onClick={() => setForwardTo(null)}>cancel</button>
          </span>
        )}
        {data.filed_activity_id !== null ? (
          <span className="rounded bg-green-100 px-2 py-1 text-green-900">
            This message has already been filed (activity {data.filed_activity_id}).
          </span>
        ) : (
          data.date_dismissed === null && (
            <button
              type="button"
              className="btn"
              disabled={activityId === null}
              title={activityId === null ? "Select an activity first" : `File under activity ${activityId}`}
              onClick={() => activityId !== null && run(() => fileInboxItem(id, activityId), `Filed under activity ${activityId}.`, true)}
            >
              File this message{activityId !== null ? ` (activity ${activityId})` : ""}
            </button>
          )
        )}
      </div>
      <h2 className="mt-4 font-semibold">Recent operations on this message</h2>
      <table className="table-grid max-w-3xl">
        <thead>
          <tr>
            <th>What</th>
            <th>When</th>
            <th>Who</th>
            <th>How</th>
          </tr>
        </thead>
        <tbody>
          {data.operations.map((op, i) => (
            <tr key={i}>
              <td>{op.operation_type}</td>
              <td className="whitespace-nowrap">{formatTimestamp(op.when_occurred)}</td>
              <td>{op.invoking_user}</td>
              <td>{op.how_invoked}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
