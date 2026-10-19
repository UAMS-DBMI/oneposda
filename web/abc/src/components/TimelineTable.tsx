import { useState } from "react";
import type { LaunchSource, TimelineEvent } from "../api/types";
import { formatDuration, formatTimestamp } from "../lib/format";
import { LaunchDialog } from "./LaunchDialog";
import { TextViewerModal } from "./TextViewerModal";
import { EmptyState } from "./ui";

/** The activity timeline: one row per report email, newest first. */
export function TimelineTable({
  events,
  activityId,
  onRefresh,
}: {
  events: TimelineEvent[];
  activityId: number;
  onRefresh: () => void;
}) {
  const [fromTimepoint, setFromTimepoint] = useState<number | null>(null);
  const [toTimepoint, setToTimepoint] = useState<number | null>(null);
  const [compare, setCompare] = useState<LaunchSource | null>(null);
  const canCompare = fromTimepoint !== null && toTimepoint !== null;
  const [viewing, setViewing] = useState<{ fileId: number; title: string } | null>(
    null,
  );
  const hasTimepoints = events.some((e) => e.timepoint_id !== null);

  return (
    <section>
      <div className="toolbar mb-2">
        <h2>Timeline</h2>
        <span className="text-slate-500">{events.length} reports, newest first</span>
        <button type="button" className="btn btn-sm" onClick={onRefresh}>
          Refresh
        </button>
        {hasTimepoints && (
          <span className="ml-auto flex items-center gap-2 text-slate-600">
            <span className="text-xs">
              Pick a <b>from</b> and a <b>to</b> timepoint, then
            </span>
            <button
              type="button"
              className={canCompare ? "btn-primary btn-sm" : "btn btn-sm"}
              disabled={!canCompare}
              title={canCompare ? `Compare timepoint ${fromTimepoint} with ${toTimepoint}` : "Pick a from and a to timepoint"}
              onClick={() =>
                canCompare &&
                setCompare({
                  type: "compare_timepoints",
                  activity_id: activityId,
                  from_timepoint_id: fromTimepoint,
                  to_timepoint_id: toTimepoint,
                })
              }
            >
              Compare timepoints
            </button>
          </span>
        )}
      </div>
      <div className="table-wrap">
        <table className="table-grid">
          <thead>
            <tr>
              <th className="num" title="subprocess_invocation_id">id</th>
              <th>operation</th>
              <th>started</th>
              <th>duration</th>
              <th className="num" title="other events overlapping this one">overlap</th>
              <th className="num" title="activity_timepoint_id">timepoint</th>
              <th className="num" title="files in the timepoint">files</th>
              <th title="compare from this timepoint">from</th>
              <th title="compare to this timepoint">to</th>
              <th>view</th>
              <th>user</th>
              <th>command</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.inbox_content_id}>
                <td className="num">{event.subprocess_invocation_id}</td>
                <td className="font-medium">{event.operation_name}</td>
                <td className="whitespace-nowrap tabular-nums">{formatTimestamp(event.started)}</td>
                <td className="whitespace-nowrap tabular-nums">{formatDuration(event.duration)}</td>
                <td className="num">{event.overlap_count > 0 ? event.overlap_count : ""}</td>
                <td className="num">{event.timepoint_id ?? ""}</td>
                <td className="num">{event.timepoint_file_count ?? ""}</td>
                <td>
                  {event.timepoint_id !== null && (
                    <input
                      type="radio"
                      name="from-timepoint"
                      aria-label={`from timepoint ${event.timepoint_id}`}
                      checked={fromTimepoint === event.timepoint_id}
                      onChange={() => setFromTimepoint(event.timepoint_id)}
                    />
                  )}
                </td>
                <td>
                  {event.timepoint_id !== null && (
                    <input
                      type="radio"
                      name="to-timepoint"
                      aria-label={`to timepoint ${event.timepoint_id}`}
                      checked={toTimepoint === event.timepoint_id}
                      onChange={() => setToTimepoint(event.timepoint_id)}
                    />
                  )}
                </td>
                <td className="space-x-1 whitespace-nowrap">
                  {event.email_file_id !== null && (
                    <button
                      type="button"
                      className="btn btn-sm"
                      title="Show the report this operation emailed"
                      onClick={() =>
                        setViewing({
                          fileId: event.email_file_id!,
                          title: `Email for ${event.subprocess_invocation_id}`,
                        })
                      }
                    >
                      email
                    </button>
                  )}
                  {event.spreadsheet_file_id !== null && (
                    <button
                      type="button"
                      className="btn btn-sm"
                      title="Show the spreadsheet this operation was given"
                      onClick={() =>
                        setViewing({
                          fileId: event.spreadsheet_file_id!,
                          title: `Input for ${event.subprocess_invocation_id}`,
                        })
                      }
                    >
                      input
                    </button>
                  )}
                </td>
                <td className="text-slate-600">{event.user_name}</td>
                <td className="mono max-w-md truncate" title={event.command_line ?? ""}>{event.command_line}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {events.length === 0 && <EmptyState>No reports for this activity yet.</EmptyState>}
      </div>
      {compare && <LaunchDialog source={compare} onClose={() => setCompare(null)} />}
      {viewing && (
        <TextViewerModal
          fileId={viewing.fileId}
          title={viewing.title}
          onClose={() => setViewing(null)}
        />
      )}
    </section>
  );
}
