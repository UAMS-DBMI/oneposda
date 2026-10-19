import type { ReactNode } from "react";
import { ApiError } from "../../api/client";

export function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return String(err);
}

export function Loading({ children = "Loading…" }: { children?: ReactNode }) {
  return (
    <p className="flex items-center gap-2 py-2 text-sm text-slate-500" role="status">
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
      {children}
    </p>
  );
}

export function ErrorMessage({ error, children }: { error?: unknown; children?: ReactNode }) {
  return (
    <div className="notice notice-danger my-2" role="alert">
      {children ?? errorText(error)}
    </div>
  );
}

export function Notice({
  tone = "info",
  children,
  onDismiss,
}: {
  tone?: "info" | "success" | "warning" | "danger";
  children: ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div className={`notice notice-${tone} my-2 flex items-start gap-3`}>
      <div className="min-w-0 flex-1">{children}</div>
      {onDismiss && (
        <button type="button" className="btn-ghost btn-sm -my-1" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="px-3 py-6 text-center text-sm text-slate-500">{children}</p>;
}
