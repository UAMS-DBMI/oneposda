import { useEffect, useState } from "react";
import { launchOperation, prepareLaunch } from "../api/abc";
import { ApiError } from "../api/client";
import type { LaunchPreview, LaunchSource, Launched } from "../api/types";
import { expandCommand, initialValues, sourceLabel } from "../lib/launch";

/**
 * The Process Operation popup: operation summary, editable arguments with
 * their provenance, the expanded command, the input preview, and Start.
 */
export function LaunchDialog({
  source,
  onClose,
  onLaunched,
}: {
  source: LaunchSource;
  onClose: () => void;
  onLaunched?: (launched: Launched) => void;
}) {
  const [preview, setPreview] = useState<LaunchPreview | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [edited, setEdited] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [launched, setLaunched] = useState<Launched | null>(null);

  useEffect(() => {
    let cancelled = false;
    prepareLaunch(source)
      .then((p) => {
        if (cancelled) return;
        setPreview(p);
        setValues(initialValues(p));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.detail : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [source]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const result = await launchOperation(source, values);
      setLaunched(result);
      onLaunched?.(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  function setValue(name: string, value: string) {
    setValues({ ...values, [name]: value });
    setEdited(new Set(edited).add(name));
  }

  const op = preview?.operation;
  const canStart = !!preview && op?.program_found !== false && !busy && !launched;

  return (
    <div
      className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-full w-full max-w-4xl flex-col overflow-auto rounded bg-white p-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Process Operation Popup"
      >
        <div className="mb-2 flex items-center gap-2">
          <h2 className="text-lg font-semibold">Process Operation Popup</h2>
          <span className="ml-auto space-x-1">
            {!launched && (
              <button type="button" className="btn-primary" onClick={start} disabled={!canStart}>
                Start
              </button>
            )}
            <button type="button" className="btn" onClick={onClose}>
              {launched ? "Close" : "Cancel"}
            </button>
          </span>
        </div>
        {error && <p className="mb-2 text-sm text-red-700">{error}</p>}
        {!preview && !error && <p className="text-gray-500">Preparing…</p>}
        {preview && op && (
          <div className="text-sm">
            <p>
              <b>Operation:</b> {op.operation_name}
            </p>
            <p className="font-mono text-xs">
              <b className="font-sans">Command:</b> {op.command_line}
            </p>
            {op.input_line_format && (
              <p className="font-mono text-xs">
                <b className="font-sans">Input line format:</b> {op.input_line_format}
              </p>
            )}
            {op.outdated && (
              <p className="font-semibold text-orange-700">
                **This operation is outdated. Speak to an administrator.**
              </p>
            )}
            {op.program_found === false && (
              <p className="font-semibold text-red-700">Program not found: {op.program}</p>
            )}
            <hr className="my-2" />
            <p className="font-semibold">Parameters:</p>
            {op.args.length === 0 && <p className="text-gray-500">none</p>}
            <table className="table-grid max-w-2xl">
              <tbody>
                {op.args.map((name) => (
                  <tr key={name}>
                    <th className="w-48">{name}</th>
                    <td>
                      <input
                        className="input w-full"
                        aria-label={name}
                        value={values[name] ?? ""}
                        onChange={(e) => setValue(name, e.target.value)}
                        disabled={!!launched}
                      />
                    </td>
                    <td className="w-40 text-gray-500">
                      {sourceLabel(preview.args[name], edited.has(name))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <hr className="my-2" />
            <p className="font-semibold">Expanded Command{op.program_found === false ? " (not found)" : ""}:</p>
            <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs">
              {expandCommand(op.command_line, values)}
            </pre>
            <hr className="my-2" />
            <p className="font-semibold">{preview.input_line_count} lines to supply as input:</p>
            <pre className="max-h-64 overflow-auto rounded bg-gray-50 p-2 text-xs">
              {preview.input_head.join("\n")}
              {preview.input_tail.length > 0 && "\n... (only first and last 10 lines shown)\n"}
              {preview.input_tail.join("\n")}
            </pre>
            {launched && (
              <div className="mt-3 rounded border border-green-300 bg-green-50 p-2">
                <p>Successfully queued background process with worker {launched.work_id}.</p>
                <p>There are {launched.pending_work} items in the worker queue.</p>
                <p className="text-gray-600">subprocess_invocation {launched.subprocess_invocation_id}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
