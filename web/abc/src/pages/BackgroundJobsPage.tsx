import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import type { BackgroundJobs } from "../api/types";
import { Badge, EmptyState, ErrorMessage, Loading, PageHeader, SegmentedControl, TimeWindowPicker, jobStatusTone } from "../components/ui";
import { formatDuration, formatTimestamp } from "../lib/format";
import { parseTimeWindow, type TimeWindow } from "../lib/timeWindow";

const MODES = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "errored", label: "Errored" },
  { value: "finished", label: "Finished" },
] as const;

type Mode = (typeof MODES)[number]["value"];

const REFRESH_MS = 10000;

function parseMode(raw: string | null): Mode {
  return MODES.some((m) => m.value === raw) ? (raw as Mode) : "all";
}

function FileLink({ fileId, label }: { fileId: number | null; label: string }) {
  if (fileId === null) return <span className="text-slate-300">–</span>;
  return (
    <a className="link tabular-nums" href={paths.fileData(fileId)} target="_blank" rel="noreferrer" title={`${label} (file ${fileId})`}>
      {fileId}
    </a>
  );
}

/** Port of Posda::BackgroundList; the list refreshes itself every 10 s. */
export function BackgroundJobsPage() {
  const [params, setParams] = useSearchParams();
  const mode = parseMode(params.get("mode"));
  const window = parseTimeWindow(params.get("in_last"));
  const { data, error, isValidating } = useSWR<BackgroundJobs>(paths.backgroundJobs(mode, window), {
    refreshInterval: REFRESH_MS,
    keepPreviousData: true,
  });

  function update(next: { mode?: Mode; in_last?: TimeWindow }) {
    const merged = { mode, in_last: window, ...next };
    const entries: [string, string][] = [];
    if (merged.mode !== "all") entries.push(["mode", merged.mode]);
    if (merged.in_last !== "12 hours") entries.push(["in_last", merged.in_last]);
    setParams(entries, { replace: true });
  }

  return (
    <div>
      <PageHeader
        title="Background processes"
        subtitle={
          <>
            Every operation launched through Posda, newest first. Refreshes every {REFRESH_MS / 1000} s
            {isValidating && <span className="ml-1 text-blue-700">· updating…</span>}
          </>
        }
        actions={
          <>
            <SegmentedControl label="Status" options={MODES} value={mode} onChange={(m) => update({ mode: m })} />
            <span className="text-slate-500">started in the last</span>
            <TimeWindowPicker value={window} onChange={(w) => update({ in_last: w })} />
          </>
        }
      />
      {error && <ErrorMessage error={error} />}
      {!data && !error && <Loading />}
      {data && (
        <div className="table-wrap">
          <table className="table-grid">
            <thead>
              <tr>
                <th className="num" title="subprocess_invocation_id">sid</th>
                <th className="num" title="work_id">wid</th>
                <th className="num" title="background_subprocess_id">bid</th>
                <th className="num" title="activity_id">activity</th>
                <th>status</th>
                <th>input</th>
                <th>stdout</th>
                <th>stderr</th>
                <th>invoker</th>
                <th>since</th>
                <th>invoked</th>
                <th>command</th>
                <th>notify</th>
                <th>node</th>
                <th>queue</th>
              </tr>
            </thead>
            <tbody>
              {data.jobs.map((job) => (
                <tr key={job.subprocess_invocation_id}>
                  <td className="num">{job.subprocess_invocation_id}</td>
                  <td className="num">{job.work_id}</td>
                  <td className="num">{job.background_subprocess_id}</td>
                  <td className="num">{job.activity_id}</td>
                  <td>
                    {job.status ? <Badge tone={jobStatusTone(job.status)}>{job.status}</Badge> : <span className="text-slate-400">queued</span>}
                  </td>
                  <td className="num"><FileLink fileId={job.input_file_id} label="Input" /></td>
                  <td className="num"><FileLink fileId={job.stdout_file_id} label="Stdout" /></td>
                  <td className="num"><FileLink fileId={job.stderr_file_id} label="Stderr" /></td>
                  <td>{job.invoking_user}</td>
                  <td className="whitespace-nowrap tabular-nums">{formatDuration(job.since_invocation)}</td>
                  <td className="whitespace-nowrap tabular-nums">{formatTimestamp(job.when_invoked)}</td>
                  <td className="mono max-w-xl truncate" title={job.command_line ?? ""}>{job.command_line}</td>
                  <td>{job.user_to_notify}</td>
                  <td className="mono">{job.node_hostname}</td>
                  <td className="mono">{job.background_queue_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.jobs.length === 0 && <EmptyState>No background processes match.</EmptyState>}
          {data.total > data.jobs.length && (
            <p className="border-t border-slate-200 px-3 py-2 text-xs text-slate-500">
              Showing the newest {data.jobs.length} of {data.total}. Narrow the status or time window to see the rest.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
