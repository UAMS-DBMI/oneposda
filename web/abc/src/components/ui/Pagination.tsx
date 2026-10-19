import { SegmentedControl } from "./SegmentedControl";

export const PAGE_SIZES = [
  { value: "30", label: "30" },
  { value: "100", label: "100" },
  { value: "500", label: "500" },
  { value: "1000", label: "1000" },
] as const;

export type PageSize = (typeof PAGE_SIZES)[number]["value"];

/** First / previous / next / last over a row window plus a page-size picker. */
export function Pagination({
  first,
  pageSize,
  total,
  partial = false,
  onFirstChange,
  onPageSizeChange,
}: {
  first: number;
  pageSize: number;
  total: number;
  partial?: boolean;
  onFirstChange: (first: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  const last = Math.max(0, total - pageSize);
  const atStart = first <= 0;
  const atEnd = first >= last;
  const shownTo = Math.min(first + pageSize, total);
  const page = Math.floor(first / pageSize) + 1;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  function go(next: number) {
    onFirstChange(Math.min(Math.max(0, next), last));
  }

  return (
    <div className="toolbar" aria-label="Pagination">
      <div className="seg seg-sm" role="group" aria-label="Page navigation">
        <button type="button" onClick={() => go(0)} disabled={atStart} title="First page" aria-label="First page">
          «
        </button>
        <button type="button" onClick={() => go(first - pageSize)} disabled={atStart} title="Previous page" aria-label="Previous page">
          ‹
        </button>
        <button type="button" onClick={() => go(first + pageSize)} disabled={atEnd} title="Next page" aria-label="Next page">
          ›
        </button>
        <button type="button" onClick={() => go(last)} disabled={atEnd} title="Last page" aria-label="Last page">
          »
        </button>
      </div>
      <span className="tabular-nums text-slate-600">
        {total === 0 ? "no rows" : `rows ${first + 1}–${shownTo} of ${total}`}
        {total > 0 && ` · page ${page} of ${pages}`}
        {partial && <span className="ml-1 text-blue-700">(more arriving)</span>}
      </span>
      <label className="ml-auto flex items-center gap-1 text-slate-600">
        Go to row
        <input
          className="input w-24 py-0.5 text-xs"
          type="number"
          min={1}
          max={Math.max(1, total)}
          value={first + 1}
          onChange={(e) => go(Number(e.target.value) - 1)}
          aria-label="First row"
        />
      </label>
      <span className="flex items-center gap-1 text-slate-600">
        Rows
        <SegmentedControl
          size="sm"
          label="Rows per page"
          options={PAGE_SIZES}
          value={String(pageSize) as PageSize}
          onChange={(v) => onPageSizeChange(Number(v))}
        />
      </span>
    </div>
  );
}
