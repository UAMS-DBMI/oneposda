import useSWR from "swr";
import { paths } from "../api/abc";
import type { FileText } from "../api/types";
import { ErrorMessage, Loading, Modal } from "./ui";

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
    <Modal
      title={title}
      subtitle={`file ${fileId}`}
      size="xl"
      onClose={onClose}
      actions={
        <a className="btn btn-sm" href={paths.fileData(fileId)} target="_blank" rel="noreferrer">
          Download
        </a>
      }
    >
      {error && <ErrorMessage error={error} />}
      {!data && !error && <Loading />}
      {data && (
        <>
          {data.truncated && (
            <p className="notice notice-warning mb-2">
              Showing the first {data.text.length} characters of {data.size} bytes. Download the file for the rest.
            </p>
          )}
          <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed">{data.text}</pre>
        </>
      )}
    </Modal>
  );
}
