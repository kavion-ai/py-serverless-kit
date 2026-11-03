const SIZES = [10, 20, 50, 100];

/**
 * Offset pagination. When `total` is unknown (token-based backends), pass
 * `hasNext` instead and the page count is hidden.
 */
export function Pagination({
  page,
  pageSize,
  total,
  hasNext,
  onPage,
  onPageSize,
}: {
  page: number;
  pageSize: number;
  total?: number | null;
  hasNext?: boolean;
  onPage: (page: number) => void;
  onPageSize?: (size: number) => void;
}) {
  const known = typeof total === "number";
  const pages = known ? Math.max(1, Math.ceil((total as number) / pageSize)) : null;
  const canNext = known ? page < (pages as number) - 1 : !!hasNext;
  const from = known && total === 0 ? 0 : page * pageSize + 1;
  const to = known ? Math.min((total as number), (page + 1) * pageSize) : null;
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="muted">
        {known ? `${from}–${to} of ${total}` : `Page ${page + 1}`}
      </span>
      <div className="pagination-controls">
        {onPageSize && (
          <select
            className="select select-sm"
            aria-label="Rows per page"
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
          >
            {SIZES.map((s) => (
              <option key={s} value={s}>
                {s} / page
              </option>
            ))}
          </select>
        )}
        <button type="button" className="btn btn-sm" disabled={page === 0} onClick={() => onPage(0)} aria-label="First page">
          «
        </button>
        <button type="button" className="btn btn-sm" disabled={page === 0} onClick={() => onPage(page - 1)}>
          Prev
        </button>
        {pages !== null && (
          <span className="muted page-of">
            {page + 1} / {pages}
          </span>
        )}
        <button type="button" className="btn btn-sm" disabled={!canNext} onClick={() => onPage(page + 1)}>
          Next
        </button>
        {pages !== null && (
          <button
            type="button"
            className="btn btn-sm"
            disabled={!canNext}
            onClick={() => onPage(pages - 1)}
            aria-label="Last page"
          >
            »
          </button>
        )}
      </div>
    </nav>
  );
}
