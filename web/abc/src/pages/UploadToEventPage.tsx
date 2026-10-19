import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { closeImportEvent, createImportEvent, uploadFilesToEvent } from "../api/abc";
import type { Uploaded } from "../api/types";
import { useMe } from "../auth/AuthGate";

/** Upload Data to Timepoint: files land in one import event, closed at the end. */
export function UploadToEventPage() {
  const me = useMe();
  const [comment, setComment] = useState(`${me.username} upload event`);
  const [eventId, setEventId] = useState<number | null>(null);
  const [uploaded, setUploaded] = useState<Uploaded[]>([]);
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function start() {
    setError(null);
    try {
      setEventId(await createImportEvent(comment));
    } catch (err) {
      setError(String(err));
    }
  }

  async function send(files: File[]) {
    if (eventId === null || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadFilesToEvent(files, eventId);
      setUploaded((current) => [...current, ...result]);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (eventId === null) return;
    setError(null);
    try {
      await closeImportEvent(eventId);
      setClosed(true);
    } catch (err) {
      setError(String(err));
    }
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    void send(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    void send(Array.from(event.dataTransfer.files));
  }

  return (
    <div>
      <h1 className="text-xl font-semibold">Upload Data to Timepoint</h1>
      {eventId === null ? (
        <div className="mt-3 flex items-end gap-2 text-sm">
          <label>
            Import event comment:{" "}
            <input className="input w-96" value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <button type="button" className="btn-primary" onClick={start}>Start upload event</button>
        </div>
      ) : (
        <div className="mt-3 text-sm">
          <p>
            Import event <b>{eventId}</b> ("{comment}"): {uploaded.length} files uploaded
            {closed && <span className="ml-2 rounded bg-green-100 px-2 py-0.5 text-green-900">closed</span>}
          </p>
          {!closed && (
            <div
              className="my-3 flex h-28 max-w-3xl cursor-pointer items-center justify-center rounded border-2 border-dashed border-gray-400 text-gray-600"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={onDrop}
              role="button"
              tabIndex={0}
            >
              {busy ? "Uploading…" : "Drop files here or click to choose"}
              <input ref={inputRef} type="file" multiple className="hidden" onChange={onPick} />
            </div>
          )}
          {uploaded.length > 0 && (
            <ul className="mb-3 max-h-64 list-disc overflow-auto pl-6">
              {uploaded.map((u, i) => (
                <li key={i}>
                  {u.name} ({u.size} bytes) → file {u.file_id}{u.created ? "" : " (already in Posda)"}
                </li>
              ))}
            </ul>
          )}
          {!closed && (
            <button type="button" className="btn-primary" onClick={finish} disabled={busy}>
              Finish (close import event)
            </button>
          )}
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    </div>
  );
}
