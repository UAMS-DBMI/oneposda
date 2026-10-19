import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR, { useSWRConfig } from "swr";
import { dismissInboxItem, fileInboxItem, forwardInboxItem, paths } from "../api/abc";
import { ApiError } from "../api/client";
import type { InboxItemDetail } from "../api/types";
import { Badge, ErrorMessage, Loading, Notice, errorText, inboxStatusTone } from "../components/ui";
import { useCurrentActivity } from "../hooks/useCurrentActivity";
import { formatTimestamp } from "../lib/format";

const URL_PATTERN = /(https?:\/\/[^\s<>"]+)/g;
const ANCHOR_PATTERN = /<a\s+href="([^"]+)"[^>]*>([^<]*)<\/a>/gi;

function urlLinks(text: string, keyBase: string) {
  return text.split(URL_PATTERN).map((part, i) =>
    /^https?:\/\//.test(part) ? (
      <a key={`${keyBase}-${i}`} href={part} className="link underline" target="_blank" rel="noreferrer">
        {part}
      </a>
    ) : (
      part
    ),
  );
}

/**
 * Report text with bare http(s) URLs and the ``<a href="…">…</a>`` anchors
 * the Perl report scripts write turned into links; everything else is
 * rendered as text, never as HTML.
 */
export function Linkified({ text }: { text: string }) {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(ANCHOR_PATTERN)) {
    const index = match.index ?? 0;
    nodes.push(...urlLinks(text.slice(last, index), `t${index}`));
    nodes.push(
      <a key={`a${index}`} href={match[1]} className="link underline" target="_blank" rel="noreferrer">
        {match[2] || match[1]}
      </a>,
    );
    last = index + match[0].length;
  }
  nodes.push(...urlLinks(text.slice(last), "tail"));
  return <>{nodes}</>;
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

  if (error instanceof ApiError && error.status === 404) return <ErrorMessage>No inbox item {itemId}.</ErrorMessage>;
  if (error) return <ErrorMessage error={error} />;
  if (!data) return <Loading />;

  async function run(action: () => Promise<void>, done: string, back = false) {
    setFailure(null);
    try {
      await action();
      setMessage(done);
      await mutate();
      await mutateGlobal(paths.inboxUnread);
      await mutateGlobal(paths.inbox());
      await mutateGlobal(paths.inbox(true));
      if (back) navigate("/inbox");
    } catch (err) {
      setFailure(errorText(err));
    }
  }

  const open = data.date_dismissed === null;

  return (
    <div className="max-w-6xl">
      <p className="mb-1 text-sm">
        <Link to="/inbox" className="link">Inbox</Link>
        <span className="mx-1 text-slate-400">/</span>
        <span className="text-slate-600">message {id}</span>
      </p>
      <div className="card mb-3 py-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="min-w-0 flex-1">
            <h1 className="truncate">{data.operation_name ?? `Message ${id}`}</h1>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
              <Badge tone={inboxStatusTone(data.current_status)}>{data.current_status ?? "unknown"}</Badge>
              <span>received {formatTimestamp(data.date_entered)}</span>
              {data.date_dismissed && <span>dismissed {formatTimestamp(data.date_dismissed)}</span>}
              {data.filed_activity_id !== null && (
                <Link to={`/activities/${data.filed_activity_id}`} className="link">
                  filed under activity {data.filed_activity_id}
                </Link>
              )}
              {data.file_id !== null && (
                <a className="link" href={paths.fileData(data.file_id)} target="_blank" rel="noreferrer">
                  download report (file {data.file_id})
                </a>
              )}
            </p>
          </div>
          <div className="toolbar">
            {open && data.filed_activity_id === null && (
              <button
                type="button"
                className="btn"
                disabled={activityId === null}
                title={activityId === null ? "Select an activity first" : `Attach this report to activity ${activityId}'s timeline and dismiss it`}
                onClick={() => activityId !== null && run(() => fileInboxItem(id, activityId), `Filed under activity ${activityId}.`, true)}
              >
                File under activity{activityId !== null ? ` #${activityId}` : ""}
              </button>
            )}
            {forwardTo === null ? (
              <button type="button" className="btn" onClick={() => setForwardTo(users.data?.[0] ?? "")}>
                Forward…
              </button>
            ) : (
              <span className="flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 p-1 text-sm">
                <span className="px-1">to</span>
                <select className="input py-0.5" value={forwardTo} onChange={(e) => setForwardTo(e.target.value)} aria-label="Forward to">
                  {(users.data ?? []).map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  disabled={!forwardTo}
                  onClick={() => run(() => forwardInboxItem(id, forwardTo), `Forwarded to ${forwardTo}.`).then(() => setForwardTo(null))}
                >
                  Send
                </button>
                <button type="button" className="btn btn-sm" onClick={() => setForwardTo(null)}>Cancel</button>
              </span>
            )}
            {open && (
              <button type="button" className="btn" onClick={() => run(() => dismissInboxItem(id), "Dismissed.", true)}>
                Dismiss
              </button>
            )}
          </div>
        </div>
      </div>
      {message && <Notice tone="success" onDismiss={() => setMessage(null)}>{message}</Notice>}
      {failure && <ErrorMessage>{failure}</ErrorMessage>}
      <pre className="pre-block mb-4 max-h-[60vh] whitespace-pre-wrap bg-white">
        {data.text !== null ? <Linkified text={data.text} /> : "(no report text)"}
        {data.text_truncated && "\n… (truncated)"}
      </pre>
      <details>
        <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-900">
          History ({data.operations.length})
        </summary>
        <div className="table-wrap mt-2 max-w-3xl">
          <table className="table-grid">
            <thead>
              <tr>
                <th>what</th>
                <th>when</th>
                <th>who</th>
                <th>how</th>
              </tr>
            </thead>
            <tbody>
              {data.operations.map((op, i) => (
                <tr key={i}>
                  <td>{op.operation_type}</td>
                  <td className="whitespace-nowrap tabular-nums">{formatTimestamp(op.when_occurred)}</td>
                  <td>{op.invoking_user}</td>
                  <td>{op.how_invoked}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
