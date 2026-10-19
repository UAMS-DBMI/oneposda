import { useEffect, useState } from "react";
import { launchOperation, prepareLaunch } from "../api/abc";
import type { LaunchPreview, LaunchSource, Launched } from "../api/types";
import { expandCommand, initialValues, sourceLabel } from "../lib/launch";
import { ErrorMessage, Loading, Modal, Notice, errorText } from "./ui";

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
        if (!cancelled) setError(errorText(err));
      });
    return () => {
      cancelled = true;
    };
  }, [source]);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const result = await launchOperation(source, values);
      setLaunched(result);
      onLaunched?.(result);
    } catch (err) {
      setError(errorText(err));
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
    <Modal
      title={op ? `Run ${op.operation_name}` : "Run operation"}
      subtitle={op?.command_line && <span className="font-mono">{op.command_line}</span>}
      onClose={onClose}
      actions={
        <>
          {!launched && (
            <button type="button" className="btn-primary" onClick={start} disabled={!canStart}>
              {busy ? "Starting…" : "Start"}
            </button>
          )}
          <button type="button" className="btn" onClick={onClose}>
            {launched ? "Close" : "Cancel"}
          </button>
        </>
      }
    >
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {!preview && !error && <Loading>Preparing…</Loading>}
      {preview && op && (
        <div className="space-y-4 text-sm">
          {op.outdated && (
            <Notice tone="warning">
              <b>This operation is outdated.</b> Speak to an administrator before relying on it.
            </Notice>
          )}
          {op.program_found === false && (
            <Notice tone="danger">
              <b>Program not found:</b> {op.program}. The worker cannot run this operation.
            </Notice>
          )}
          {launched && (
            <Notice tone="success">
              <p>Successfully queued background process with worker {launched.work_id}.</p>
              <p>There are {launched.pending_work} items in the worker queue.</p>
              <p className="text-xs text-slate-600">subprocess_invocation {launched.subprocess_invocation_id}</p>
            </Notice>
          )}
          <section>
            <h3 className="mb-1">Parameters</h3>
            {op.args.length === 0 && <p className="text-slate-500">This operation takes no parameters.</p>}
            {op.args.length > 0 && (
              <div className="grid gap-1.5">
                {op.args.map((name) => (
                  <label key={name} className="grid grid-cols-[11rem_minmax(0,1fr)_10rem] items-center gap-3">
                    <span className="truncate font-medium text-slate-700" title={name}>{name}</span>
                    <input
                      className="input py-0.5"
                      aria-label={name}
                      value={values[name] ?? ""}
                      onChange={(e) => setValue(name, e.target.value)}
                      disabled={!!launched}
                    />
                    <span className="truncate text-xs text-slate-500">{sourceLabel(preview.args[name], edited.has(name))}</span>
                  </label>
                ))}
              </div>
            )}
          </section>
          <section>
            <h3 className="mb-1">Command the worker will run{op.program_found === false ? " (not found)" : ""}</h3>
            <pre className="pre-block whitespace-pre-wrap">{expandCommand(op.command_line, values)}</pre>
          </section>
          <section>
            <h3 className="mb-1">
              {preview.input_line_count} lines to supply as input:
              {op.input_line_format && (
                <span className="ml-2 font-mono text-xs font-normal text-slate-500">{op.input_line_format}</span>
              )}
            </h3>
            <pre className="pre-block max-h-64">
              {preview.input_head.join("\n")}
              {preview.input_tail.length > 0 && "\n... (only first and last 10 lines shown)\n"}
              {preview.input_tail.join("\n")}
            </pre>
          </section>
        </div>
      )}
    </Modal>
  );
}
