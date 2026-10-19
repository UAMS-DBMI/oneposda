import { useState } from "react";
import useSWR from "swr";
import { paths } from "../api/abc";
import type { BackgroundJobs } from "../api/types";
import { formatDuration, formatTimestamp } from "../lib/format";

const MODES = ["all", "running", "errored", "finished"] as const;

function FileLink({ fileId, label }: { fileId: number | null; label: string }) {
  if (fileId === null) return null;
  return (
    <a className="btn" href={paths.fileData(fileId)} target="_blank" rel="noreferrer" title={label}>
      {fileId}
    </a>
  );
}

/** Port of Posda::BackgroundList. */
export function BackgroundJobsPage() {
  const [mode, setMode] = useState<(typeof MODES)[number]>("all");
  const [useWindow, setUseWindow] = useState(true);
  const [inLast, setInLast] = useState("12 hours");
  const [refresh, setRefresh] = useState(false);
  const { data, error } = useSWR<BackgroundJobs>(paths.backgroundJobs(mode, useWindow ? inLast : ""), {
    refreshInterval: refresh ? 10000 : 0,
  });

  return (
    <div>
      <h1 className="text-xl font-semibold">Background Process Lister</h1>
      <div className="my-3 flex flex-wrap items-center gap-3 text-sm">
        {MODES.map((m) => (
          <label key={m} className="flex items-center gap-1">
            <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />
            {m}
          </label>
        ))}
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={useWindow} onChange={(e) => setUseWindow(e.target.checked)} />
          In last:
        </label>
        <input className="input w-32" value={inLast} disabled={!useWindow} onChange={(e) => setInLast(e.target.value)} />
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} />
          Refresh
        </label>
      </div>
      {error && <p className="text-red-700">{String(error)}</p>}
      <div className="overflow-x-auto">
        <table className="table-grid">
          <thead>
            <tr>
              <th>sid</th><th>wid</th><th>bid</th><th>aid</th><th>status</th><th>input</th><th>stdout</th><th>stderr</th>
              <th>invoker</th><th>since</th><th>command_line</th><th>invoked</th><th>notify</th><th>node_hostname</th><th>queue</th>
            </tr>
          </thead>
          <tbody>
            {(data?.jobs ?? []).map((job) => (
              <tr key={job.subprocess_invocation_id}>
                <td>{job.subprocess_invocation_id}</td>
                <td>{job.work_id}</td>
                <td>{job.background_subprocess_id}</td>
                <td>{job.activity_id}</td>
                <td className={job.status === "errored" ? "text-red-700" : ""}>{job.status}</td>
                <td><FileLink fileId={job.input_file_id} label="Input" /></td>
                <td><FileLink fileId={job.stdout_file_id} label="Stdout" /></td>
                <td><FileLink fileId={job.stderr_file_id} label="Stderr" /></td>
                <td>{job.invoking_user}</td>
                <td className="whitespace-nowrap">{formatDuration(job.since_invocation)}</td>
                <td className="font-mono text-xs">{job.command_line}</td>
                <td className="whitespace-nowrap">{formatTimestamp(job.when_invoked)}</td>
                <td>{job.user_to_notify}</td>
                <td>{job.node_hostname}</td>
                <td>{job.background_queue_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && data.total > data.jobs.length && (
        <p className="mt-2 text-sm text-gray-600">Only {data.jobs.length} of {data.total} printed</p>
      )}
    </div>
  );
}
