import useSWR from "swr";
import { paths } from "../api/abc";
import type { FileText } from "../api/types";

/** Shows a Posda file as text (report emails, operation inputs). */
export function TextViewerModal({
  fileId,
  title,
  onClose,
}: {
  fileId: number;
  title: string;
  onClose: () => void;
}) {
  const { data, error } = useSWR<FileText>(paths.fileText(fileId));

  return (
    <div
      className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-full w-full max-w-5xl flex-col rounded bg-white shadow-lg"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={title}
      >
        <div className="flex items-center border-b border-gray-300 px-4 py-2">
          <span className="font-semibold">{title}</span>
          <span className="ml-2 text-sm text-gray-500">file {fileId}</span>
          <a
            className="ml-4 text-sm text-blue-700"
            href={`/papi/v1/files/${fileId}/data`}
            target="_blank"
            rel="noreferrer"
          >
            download
          </a>
          <button type="button" className="btn ml-auto" onClick={onClose}>
            close
          </button>
        </div>
        <div className="overflow-auto p-4">
          {error && <p className="text-red-700">{String(error)}</p>}
          {!data && !error && <p className="text-gray-500">Loading…</p>}
          {data && (
            <>
              {data.truncated && (
                <p className="mb-2 text-sm text-orange-700">
                  Showing the first {data.text.length} characters of {data.size} bytes.
                </p>
              )}
              <pre className="whitespace-pre-wrap font-mono text-xs">{data.text}</pre>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
