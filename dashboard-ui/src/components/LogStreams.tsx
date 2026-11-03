import { useCallback, useEffect, useState } from "react";
import type { LogDeleteRequest, LogDeleteResult, LogStream, LogStreamsResponse } from "../types";
import { formatDate } from "../format";
import { EmptyState, ErrorBanner, Spinner } from "./Feedback";
import { Select } from "./Inputs";

type Confirm = (message: string) => Promise<boolean>;

const browserConfirm: Confirm = (message) => Promise.resolve(window.confirm(message));

function size(stream: LogStream): string {
  if (typeof stream.count === "number") return `${stream.count} entries`;
  if (typeof stream.bytes === "number") {
    const b = stream.bytes;
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1024 / 1024).toFixed(1)} MB`;
  }
  return "";
}

/**
 * Log streams of a deployment (CloudWatch streams, or one entry per function on an
 * on-prem host) with select / delete. Talks only through the injected callbacks, so
 * the dashboard and the studio share it.
 */
export function LogStreams({
  fetchStreams,
  deleteStreams,
  functions,
  confirm = browserConfirm,
  onDeleted,
}: {
  fetchStreams: (fn?: string) => Promise<LogStreamsResponse>;
  deleteStreams: (p: LogDeleteRequest) => Promise<LogDeleteResult>;
  functions: string[];
  confirm?: Confirm;
  onDeleted?: (result: LogDeleteResult) => void;
}) {
  const [fn, setFn] = useState("");
  const [data, setData] = useState<LogStreamsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    fetchStreams(fn || undefined)
      .then((r) => {
        if (!live) return;
        setData(r);
        setSelected((prev) => new Set(Array.from(prev).filter((id) => (r.items || []).some((i) => i.id === id))));
      })
      .catch((err: unknown) => live && setError(err instanceof Error ? err.message : String(err)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [fetchStreams, fn, attempt]);

  const reload = useCallback(() => setAttempt((a) => a + 1), []);
  const items = data?.items || [];
  const allChecked = items.length > 0 && items.every((i) => selected.has(i.id));

  const run = async (request: LogDeleteRequest, message: string) => {
    if (!(await confirm(message))) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await deleteStreams(request);
      const errors = result.errors || [];
      setNotice(`Deleted ${result.deleted}${errors.length ? `, ${errors.length} failed` : ""}.`);
      if (errors.length) setError(errors.slice(0, 3).join("; "));
      setSelected(new Set());
      onDeleted?.(result);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  if (data && !data.supported) {
    return <EmptyState title="Log streams unavailable">{data.reason || "Not available for this deployment."}</EmptyState>;
  }
  const canDelete = !!data?.can_delete;

  return (
    <div className="logstreams">
      <div className="toolbar">
        <Select label="Function" allLabel="All functions" value={fn} onChange={setFn} options={functions} />
        <button type="button" className="btn" onClick={reload} disabled={loading}>
          ↻ Refresh
        </button>
        {canDelete && (
          <>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy || !selected.size}
              onClick={() =>
                void run({ ids: Array.from(selected) }, `Delete ${selected.size} selected log stream(s)? This cannot be undone.`)
              }
            >
              Delete selected{selected.size ? ` (${selected.size})` : ""}
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy || !items.length}
              onClick={() =>
                void run(
                  fn ? { function: fn } : { all: true },
                  fn ? `Delete every log stream of ${fn}? This cannot be undone.` : "Delete ALL logs of this deployment? This cannot be undone.",
                )
              }
            >
              {fn ? `Delete all logs of ${fn}` : "Delete all logs"}
            </button>
          </>
        )}
      </div>
      {!canDelete && data?.reason && <div className="muted small">{data.reason}</div>}
      {notice && <div className="muted small">{notice}</div>}
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && !data ? (
        <Spinner label="Loading log streams…" />
      ) : !items.length ? (
        <EmptyState title="No log streams">Logs appear here once the functions have run.</EmptyState>
      ) : (
        <table className="table logstreams-table">
          <thead>
            <tr>
              {canDelete && (
                <th className="check-col">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={allChecked}
                    onChange={(e) => setSelected(e.target.checked ? new Set(items.map((i) => i.id)) : new Set())}
                  />
                </th>
              )}
              <th>Function</th>
              <th>Stream</th>
              <th>Last event</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id} className={selected.has(s.id) ? "selected" : undefined}>
                {canDelete && (
                  <td className="check-col">
                    <input
                      type="checkbox"
                      aria-label={`Select ${s.name || s.id}`}
                      checked={selected.has(s.id)}
                      onChange={(e) =>
                        setSelected((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(s.id);
                          else next.delete(s.id);
                          return next;
                        })
                      }
                    />
                  </td>
                )}
                <td>{s.function || <span className="muted">host</span>}</td>
                <td className="mono small">{s.name || s.id}</td>
                <td className="small">{formatDate(s.last)}</td>
                <td className="small">{size(s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
