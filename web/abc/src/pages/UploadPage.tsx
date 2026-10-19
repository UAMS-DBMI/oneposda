import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { paths, uploadFiles } from "../api/abc";
import { api } from "../api/client";
import type { Candidates, LaunchSource, Sheet, Uploaded } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { CandidateOperationsTable } from "../components/CandidateOperationsTable";
import { LaunchDialog } from "../components/LaunchDialog";

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

/** The Upload page: drop files in, see what was imported, chain spreadsheets. */
export function UploadPage() {
  const me = useMe();
  const [params] = useSearchParams();
  const requestedOperation = params.get("operation");
  const [entries, setEntries] = useState<Entry[]>(() => loadEntries(me.username));
  const [busy, setBusy] = useState(false);
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
        ...current,
        ...uploaded.map((u) => ({ ...u, description: u.mime_type ?? "", selected: false })),
      ]);
    } catch (err) {
      setError(String(err));
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
      setError(String(err));
    }
  }

  function update(index: number, patch: Partial<Entry>) {
    setEntries(entries.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  }

  return (
    <div>
      <h1 className="text-xl font-semibold">Upload</h1>
      {requestedOperation && (
        <p className="my-2 text-sm text-orange-700">
          Upload a spreadsheet for <b>{requestedOperation}</b>, then press chain on it.
        </p>
      )}
      <div
        className="my-3 flex h-28 max-w-3xl cursor-pointer items-center justify-center rounded border-2 border-dashed border-gray-400 text-sm text-gray-600"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
      >
        {busy ? "Uploading…" : "Drop files here or click to choose"}
        <input ref={inputRef} type="file" multiple className="hidden" onChange={onPick} data-testid="file-input" />
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {entries.length === 0 ? (
        <p className="text-sm text-gray-500">No files have been uploaded</p>
      ) : (
        <table className="table-grid max-w-5xl">
          <thead>
            <tr>
              <th>file_name</th>
              <th>size</th>
              <th>mime_type</th>
              <th>description</th>
              <th>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => setEntries(entries.filter((e) => !e.selected))}
                >
                  Dismiss
                </button>
              </th>
              <th>file_id</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              <tr key={`${entry.file_id}-${index}`}>
                <td>{entry.name}</td>
                <td>{entry.size}</td>
                <td>
                  {entry.mime_type}{" "}
                  {entry.is_spreadsheet && (
                    <button type="button" className="btn-primary ml-1" onClick={() => chain(entry)}>
                      chain
                    </button>
                  )}
                </td>
                <td>
                  <input
                    className="input w-64"
                    value={entry.description}
                    onChange={(e) => update(index, { description: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={entry.selected}
                    onChange={(e) => update(index, { selected: e.target.checked })}
                  />
                </td>
                <td>
                  <a className="text-blue-700" href={`/papi/v1/files/${entry.file_id}/data`} target="_blank" rel="noreferrer">
                    {entry.file_id}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {chaining && (
        <div className="mt-4">
          <h2 className="font-semibold">This Spreadsheet Has No Operation</h2>
          <p className="mb-2 text-sm">
            Columns: {chaining.candidates.columns.join(", ")} ({chaining.candidates.row_count} rows). Choose one from the table below.
          </p>
          <CandidateOperationsTable
            candidates={chaining.candidates.candidates}
            onChoose={(name) => {
              setSource({ type: "spreadsheet", file_id: chaining.fileId, operation: name });
              setChaining(null);
            }}
          />
        </div>
      )}
      {source && <LaunchDialog source={source} onClose={() => setSource(null)} />}
    </div>
  );
}
