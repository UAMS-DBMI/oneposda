import { useState } from "react";
import type { TimelineEvent } from "../api/types";
import { formatDuration, formatTimestamp } from "../lib/format";
import { TextViewerModal } from "./TextViewerModal";

/** The activity timeline: one row per report email, newest first. */
export function TimelineTable({
  events,
  onRefresh,
}: {
  events: TimelineEvent[];
  onRefresh: () => void;
}) {
  const [fromTimepoint, setFromTimepoint] = useState<number | null>(null);
  const [toTimepoint, setToTimepoint] = useState<number | null>(null);
  const [viewing, setViewing] = useState<{ fileId: number; title: string } | null>(
    null,
  );

  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-sm">
        <span className="font-semibold">Timeline</span>
        <button type="button" className="btn" onClick={onRefresh}>
          refresh
        </button>
      </div>
      <table className="table-grid">
        <thead>
          <tr>
            <th rowSpan={2}>id</th>
            <th rowSpan={2}>operation</th>
            <th rowSpan={2}>start</th>
            <th rowSpan={2}>duration</th>
            <th rowSpan={2} title="other events overlapping this one">
              ol
            </th>
            <th>tp</th>
            <th colSpan={2}>
              <button
                type="button"
                className="btn"
                disabled
                title="Compare timepoints arrives with operations in phase 3"
              >
                cmp
              </button>
            </th>
            <th>tp</th>
            <th rowSpan={2}>view</th>
            <th rowSpan={2}>user</th>
            <th rowSpan={2}>command</th>
          </tr>
          <tr>
            <th>id</th>
            <th>fr</th>
            <th>to</th>
            <th>files</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.inbox_content_id}>
              <td>{event.subprocess_invocation_id}</td>
              <td>{event.operation_name}</td>
              <td className="whitespace-nowrap">{formatTimestamp(event.started)}</td>
              <td className="whitespace-nowrap">{formatDuration(event.duration)}</td>
              <td>{event.overlap_count}</td>
              <td>{event.timepoint_id ?? ""}</td>
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
              <td>{event.timepoint_file_count ?? ""}</td>
              <td className="whitespace-nowrap">
                {event.email_file_id !== null && (
                  <button
                    type="button"
                    className="btn mr-1"
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
                    className="btn"
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
              <td>{event.user_name}</td>
              <td className="font-mono text-xs">{event.command_line}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {events.length === 0 && (
        <p className="mt-2 text-sm text-gray-600">No reports for this activity yet.</p>
      )}
      {viewing && (
        <TextViewerModal
          fileId={viewing.fileId}
          title={viewing.title}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  );
}
