import { useEffect, useMemo, useState, type ReactNode } from "react";
import { EmptyState } from "./Feedback";
import { Pagination } from "./Pagination";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Value used for sorting; omit to make the column unsortable. */
  sortValue?: (row: T) => string | number | null | undefined;
  className?: string;
}

/**
 * Sortable table with client-side pagination. For server-side pagination,
 * render the rows yourself with `paginate={false}` and a separate <Pagination>.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  emptyTitle = "Nothing to show",
  emptyHint,
  initialPageSize = 20,
  paginate = true,
  selectedKey,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyTitle?: string;
  emptyHint?: ReactNode;
  initialPageSize?: number;
  paginate?: boolean;
  selectedKey?: string | null;
}) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(initialPageSize);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col || !col.sortValue) return rows;
    const get = col.sortValue;
    return [...rows].sort((a, b) => {
      const x = get(a);
      const y = get(b);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (x < y ? -1 : 1) * sort.dir;
    });
  }, [rows, sort, columns]);

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  useEffect(() => {
    if (page > pages - 1) setPage(pages - 1);
  }, [page, pages]);
  const visible = paginate ? sorted.slice(page * pageSize, (page + 1) * pageSize) : sorted;

  if (!rows.length) return <EmptyState title={emptyTitle}>{emptyHint}</EmptyState>;

  const toggle = (key: string) =>
    setSort((s) => (s && s.key === key ? (s.dir === 1 ? { key, dir: -1 } : null) : { key, dir: 1 }));

  return (
    <div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {columns.map((c) => {
                const active = sort && sort.key === c.key;
                return (
                  <th
                    key={c.key}
                    className={c.className}
                    aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
                  >
                    {c.sortValue ? (
                      <button type="button" className="th-sort" onClick={() => toggle(c.key)}>
                        {c.header}
                        <span className="sort-mark" aria-hidden="true">
                          {active ? (sort.dir === 1 ? "▲" : "▼") : "↕"}
                        </span>
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const key = rowKey(row);
              return (
                <tr
                  key={key}
                  className={[onRowClick ? "clickable" : "", selectedKey === key ? "selected" : ""].join(" ").trim()}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onRowClick(row);
                          }
                        }
                      : undefined
                  }
                  tabIndex={onRowClick ? 0 : undefined}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={c.className} data-label={c.header}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {paginate && sorted.length > Math.min(pageSize, 10) && (
        <Pagination
          page={page}
          pageSize={pageSize}
          total={sorted.length}
          onPage={setPage}
          onPageSize={(s) => {
            setPageSize(s);
            setPage(0);
          }}
        />
      )}
    </div>
  );
}
