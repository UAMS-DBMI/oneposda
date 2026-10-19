import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { paths, uploadFiles } from "../api/abc";
import { api } from "../api/client";
import type { Candidates, LaunchSource, Sheet, Uploaded } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { CandidateOperationsTable } from "../components/CandidateOperationsTable";
import { LaunchDialog } from "../components/LaunchDialog";
import { Badge, EmptyState, ErrorMessage, Notice, PageHeader, errorText } from "../components/ui";

interface Entry extends Uploaded {
  description: string;
  selected: boolean;
}

function storageKey(username: string): string {
  return `abc.uploads.${username}`;
}

function loadEntries(username: string): Entry[] {
  try {
    const raw = localStorage.getItem(storageKey(username));
    return raw ? (JSON.parse(raw) as Entry[]) : [];
  } catch {
    return [];
  }
}

function saveEntries(username: string, entries: Entry[]): void {
  try {
    localStorage.setItem(storageKey(username), JSON.stringify(entries));
  } catch {
    // storage unavailable; the list just will not survive a reload
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** The Upload page: drop files in, see what was imported, chain spreadsheets. */
export function UploadPage() {
  const me = useMe();
  const [params] = useSearchParams();
  const requestedOperation = params.get("operation");
  const [entries, setEntries] = useState<Entry[]>(() => loadEntries(me.username));
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chaining, setChaining] = useState<{ fileId: number; candidates: Candidates } | null>(null);
  const [source, setSource] = useState<LaunchSource | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => saveEntries(me.username, entries), [me.username, entries]);

  async function send(files: File[]) {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const uploaded = await uploadFiles(files);
      setEntries((current) => [
        ...uploaded.map((u) => ({ ...u, description: u.mime_type ?? "", selected: false })),
        ...current,
      ]);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    void send(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void send(Array.from(event.dataTransfer.files));
  }

  async function chain(entry: Entry) {
    setError(null);
    try {
      const sheet = await api.get<Sheet>(paths.sheet(entry.file_id));
      const operation = sheet.named_operation ?? requestedOperation;
      if (operation) {
        setSource({ type: "spreadsheet", file_id: entry.file_id, operation });
        return;
      }
      const candidates = await api.get<Candidates>(paths.candidatesForFile(entry.file_id));
      setChaining({ fileId: entry.file_id, candidates });
    } catch (err) {
      setError(errorText(err));
    }
  }

  function update(index: number, patch: Partial<Entry>) {
    setEntries(entries.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  }

  const selectedCount = entries.filter((e) => e.selected).length;

  return (
    <div className="max-w-6xl">
      <PageHeader
        title="Upload"
        subtitle="Upload spreadsheets (CSV or XLSX) and send them to an operation. A spreadsheet with an Operation column picks its own."
      />
      {requestedOperation && (
        <Notice tone="info">
          Upload a spreadsheet for <b>{requestedOperation}</b>, then press <b>Process</b> on it.
        </Notice>
      )}
      <div
        className={`dropzone my-3 h-28 ${dragging ? "border-blue-500 bg-blue-50" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
      >
        {busy ? "Uploading…" : "Drop files here or click to choose"}
        <input ref={inputRef} type="file" multiple className="hidden" onChange={onPick} data-testid="file-input" />
      </div>
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <div className="table-wrap">
        <table className="table-grid">
          <thead>
            <tr>
              <th className="w-6">
                <input
                  type="checkbox"
                  aria-label="select all"
                  checked={entries.length > 0 && selectedCount === entries.length}
                  onChange={(e) => setEntries(entries.map((entry) => ({ ...entry, selected: e.target.checked })))}
                />
              </th>
              <th>file</th>
              <th className="num">size</th>
              <th>type</th>
              <th>note</th>
              <th className="num">file id</th>
              <th className="text-right">
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={selectedCount === 0}
                  onClick={() => setEntries(entries.filter((e) => !e.selected))}
                  title="Remove the selected rows from this list (the files stay in Posda)"
                >
                  Remove selected
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              <tr key={`${entry.file_id}-${index}`} className={entry.selected ? "is-selected" : ""}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`select ${entry.name}`}
                    checked={entry.selected}
                    onChange={(e) => update(index, { selected: e.target.checked })}
                  />
                </td>
                <td className="font-medium">{entry.name}</td>
                <td className="num whitespace-nowrap">{formatSize(entry.size)}</td>
                <td>
                  {entry.is_spreadsheet ? <Badge tone="info">spreadsheet</Badge> : <span className="text-slate-500">{entry.mime_type}</span>}
                </td>
                <td>
                  <input
                    className="input w-56 py-0.5"
                    value={entry.description}
                    onChange={(e) => update(index, { description: e.target.value })}
                    aria-label={`note for ${entry.name}`}
                  />
                </td>
                <td className="num">
                  <a className="link" href={paths.fileData(entry.file_id)} target="_blank" rel="noreferrer">
                    {entry.file_id}
                  </a>
                </td>
                <td className="text-right">
                  {entry.is_spreadsheet && (
                    <button type="button" className="btn-primary btn-sm" onClick={() => chain(entry)} title="Send this spreadsheet to an operation">
                      Process
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {entries.length === 0 && <EmptyState>No files have been uploaded in this browser yet.</EmptyState>}
      </div>
      {chaining && (
        <section className="card mt-4">
          <div className="mb-2 flex items-start justify-between gap-3">
            <div>
              <h2>This spreadsheet names no operation</h2>
              <p className="text-sm text-slate-600">
                Columns: {chaining.candidates.columns.join(", ")} ({chaining.candidates.row_count} rows). Choose an operation that takes them.
              </p>
            </div>
            <button type="button" className="btn btn-sm" onClick={() => setChaining(null)}>Close</button>
          </div>
          <CandidateOperationsTable
            candidates={chaining.candidates.candidates}
            onChoose={(name) => {
              setSource({ type: "spreadsheet", file_id: chaining.fileId, operation: name });
              setChaining(null);
            }}
          />
        </section>
      )}
      {source && <LaunchDialog source={source} onClose={() => setSource(null)} />}
    </div>
  );
}
