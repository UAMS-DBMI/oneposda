import { useEffect, type ReactNode } from "react";

/** Overlay dialog: closes on Escape and on a click outside the panel. */
export function Modal({
  title,
  subtitle,
  actions,
  onClose,
  size = "lg",
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  onClose: () => void;
  size?: "md" | "lg" | "xl";
  children: ReactNode;
}) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const width = { md: "max-w-2xl", lg: "max-w-4xl", xl: "max-w-6xl" }[size];

  return (
    <div
      className="fixed inset-0 z-20 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 pt-10 backdrop-blur-[1px] sm:p-8"
      onClick={onClose}
      role="presentation"
    >
      <div
        className={`flex max-h-[calc(100vh-4rem)] w-full ${width} flex-col rounded-lg bg-white shadow-xl`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="truncate">{title}</h2>
            {subtitle && <div className="text-xs text-slate-500">{subtitle}</div>}
          </div>
          {actions}
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close dialog">
            ✕
          </button>
        </div>
        <div className="min-h-0 overflow-auto p-4">{children}</div>
      </div>
    </div>
  );
}
