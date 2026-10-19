import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { closeImportEvent, createImportEvent, uploadFilesToEvent } from "../api/abc";
import type { Uploaded } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { Badge, ErrorMessage, PageHeader, errorText } from "../components/ui";

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
      setError(errorText(err));
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
      setError(errorText(err));
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
      setError(errorText(err));
    }
  }

  function reset() {
    setEventId(null);
    setUploaded([]);
    setClosed(false);
    setComment(`${me.username} upload event`);
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    void send(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    void send(Array.from(event.dataTransfer.files));
  }

  const steps = [
    { label: "Start an import event", done: eventId !== null },
    { label: "Upload the files", done: uploaded.length > 0 },
    { label: "Close the event", done: closed },
  ];

  return (
    <div className="max-w-4xl">
      <PageHeader
        title="Upload data"
        subtitle="Import files into Posda under one import event, which you then turn into a timepoint from the Workflow page."
      />
      <ol className="mb-4 flex flex-wrap gap-4 text-sm">
        {steps.map((step, i) => (
          <li key={step.label} className="flex items-center gap-2">
            <span
              className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold ${
                step.done ? "bg-green-600 text-white" : "bg-slate-200 text-slate-700"
              }`}
            >
              {step.done ? "✓" : i + 1}
            </span>
            <span className={step.done ? "text-slate-500" : ""}>{step.label}</span>
          </li>
        ))}
      </ol>
      {eventId === null ? (
        <form
          className="card flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void start();
          }}
        >
          <label className="field min-w-0 flex-1">
            <span>Import event comment</span>
            <input className="input" value={comment} onChange={(e) => setComment(e.target.value)} autoFocus />
          </label>
          <button type="submit" className="btn-primary" disabled={!comment.trim()}>
            Start upload event
          </button>
        </form>
      ) : (
        <div className="card">
          <p className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <span>
              Import event <b>{eventId}</b> · “{comment}”
            </span>
            <Badge tone={closed ? "success" : "running"}>{closed ? "closed" : "open"}</Badge>
            <span className="text-slate-500">{uploaded.length} files uploaded</span>
          </p>
          {!closed && (
            <div
              className="dropzone mb-3 h-28"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={onDrop}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
              }}
            >
              {busy ? "Uploading…" : "Drop files here or click to choose"}
              <input ref={inputRef} type="file" multiple className="hidden" onChange={onPick} />
            </div>
          )}
          {uploaded.length > 0 && (
            <div className="table-wrap mb-3 max-h-72 overflow-auto">
              <table className="table-grid">
                <thead>
                  <tr>
                    <th>file</th>
                    <th className="num">bytes</th>
                    <th className="num">file id</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {uploaded.map((u, i) => (
                    <tr key={i}>
                      <td>{u.name}</td>
                      <td className="num">{u.size}</td>
                      <td className="num">{u.file_id}</td>
                      <td className="text-slate-500">{u.created ? "" : "already in Posda"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="toolbar">
            {!closed ? (
              <button type="button" className="btn-primary" onClick={finish} disabled={busy}>
                Finish and close the event
              </button>
            ) : (
              <>
                <span className="text-sm text-slate-600">
                  Done. Use <b>Create Timepoint From Import Event Id</b> on the Workflow page with event {eventId}.
                </span>
                <button type="button" className="btn" onClick={reset}>Start another</button>
              </>
            )}
          </div>
        </div>
      )}
      {error && <ErrorMessage>{error}</ErrorMessage>}
    </div>
  );
}
