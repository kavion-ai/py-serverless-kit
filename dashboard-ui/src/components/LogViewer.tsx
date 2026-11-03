import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { LogEntry, LogsResponse } from "../types";
import { formatTime, levelTone, safeUrl } from "../format";
import { ErrorBanner, Spinner, EmptyState } from "./Feedback";
import { SearchInput, Select } from "./Inputs";

export interface LogFilters {
  level: string;
  function: string;
  source: string;
  q: string;
}

type Fetcher = (p: { since: number; limit: number } & Partial<LogFilters>) => Promise<LogsResponse>;

const PAGE = 200;
const MAX_KEPT = 3000;
const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];
const SOURCES = ["function", "invocation", "stdout", "stderr", "host"];

function filtersOf(f: LogFilters): Partial<LogFilters> {
  const out: Partial<LogFilters> = {};
  (Object.keys(f) as (keyof LogFilters)[]).forEach((k) => {
    if (f[k]) out[k] = f[k];
  });
  return out;
}

/**
 * Live tail of a log endpoint that pages by sequence number (`since` exclusive,
 * ascending). Filters are applied by the server; the viewer keeps the newest
 * MAX_KEPT entries.
 */
export function LogViewer({
  fetchLogs,
  functions,
  interval = 2000,
}: {
  fetchLogs: Fetcher;
  functions: string[];
  interval?: number;
}) {
  const [filters, setFilters] = useState<LogFilters>({ level: "", function: "", source: "", q: "" });
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [oldest, setOldest] = useState<number>(0);
  const [paused, setPaused] = useState(false);
  const [follow, setFollow] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unsupported, setUnsupported] = useState<string | null>(null);
  const [consoleUrl, setConsoleUrl] = useState<string | null>(null);
  const [mode, setMode] = useState<"seq" | "time">("seq");
  const [loading, setLoading] = useState(true);
  const [olderLoading, setOlderLoading] = useState(false);
  const nextRef = useRef(0);
  const box = useRef<HTMLDivElement>(null);
  const fetchRef = useRef(fetchLogs);
  fetchRef.current = fetchLogs;
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  // Debounce the free-text filter.
  useEffect(() => {
    const t = window.setTimeout(() => setFilters((f) => (f.q === query ? f : { ...f, q: query })), 350);
    return () => window.clearTimeout(t);
  }, [query]);

  const append = useCallback((items: LogEntry[]) => {
    if (!items.length) return;
    setEntries((prev) => {
      const last = prev.length ? prev[prev.length - 1].seq : -1;
      const merged = prev.concat(items.filter((e) => e.seq > last));
      return merged.length > MAX_KEPT ? merged.slice(merged.length - MAX_KEPT) : merged;
    });
  }, []);

  // Initial tail load whenever the filters change, then poll.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let failures = 0;
    const extra = filtersOf(filters);
    setEntries([]);
    setLoading(true);
    setError(null);

    const poll = async () => {
      if (cancelled) return;
      if (!pausedRef.current && document.visibilityState !== "hidden") {
        try {
          const resp = await fetchRef.current({ since: nextRef.current, limit: PAGE, ...extra });
          if (cancelled) return;
          if (!resp.supported) {
            setUnsupported(resp.reason || "Logs are not available for this deployment.");
            setConsoleUrl(safeUrl(resp.console));
            return;
          }
          append(resp.entries || []);
          if (typeof resp.next === "number") nextRef.current = Math.max(nextRef.current, resp.next);
          if (typeof resp.oldest === "number") setOldest(resp.oldest);
          setError(null);
          failures = 0;
          // More than one page arrived: keep reading without waiting.
          if ((resp.entries || []).length >= PAGE) {
            timer = window.setTimeout(poll, 50);
            return;
          }
        } catch (err) {
          if (cancelled) return;
          failures += 1;
          setError(err instanceof Error ? err.message : String(err));
        }
      }
      timer = window.setTimeout(poll, interval * Math.min(8, 2 ** Math.max(0, failures - 1)));
    };

    (async () => {
      try {
        // Find the newest sequence number, then read the last page before it.
        const head = await fetchRef.current({ since: 0, limit: 1, ...extra });
        if (cancelled) return;
        if (!head.supported) {
          setUnsupported(head.reason || "Logs are not available for this deployment.");
          setConsoleUrl(safeUrl(head.console));
          setLoading(false);
          return;
        }
        setUnsupported(null);
        setConsoleUrl(safeUrl(head.console));
        const timeMode = head.mode === "time";
        setMode(timeMode ? "time" : "seq");
        if (timeMode) {
          // Cloud logs page by timestamp: 0 asks the server for the recent window.
          nextRef.current = 0;
        } else {
          const latest = typeof head.next === "number" ? head.next : 0;
          nextRef.current = Math.max(0, latest - PAGE);
          if (typeof head.oldest === "number") setOldest(head.oldest);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        nextRef.current = 0;
      }
      setLoading(false);
      poll();
    })();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [filters, interval, append]);

  const loadOlder = async () => {
    if (!entries.length) return;
    const first = entries[0].seq;
    setOlderLoading(true);
    try {
      const since = Math.max(0, first - 1 - PAGE);
      const resp = await fetchRef.current({ since, limit: PAGE, ...filtersOf(filters) });
      const older = (resp.entries || []).filter((e) => e.seq < first);
      setFollow(false);
      setEntries((prev) => older.concat(prev));
      if (typeof resp.oldest === "number") setOldest(resp.oldest);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setOlderLoading(false);
    }
  };

  useLayoutEffect(() => {
    const el = box.current;
    if (el && follow) el.scrollTop = el.scrollHeight;
  }, [entries, follow]);

  const onScroll = () => {
    const el = box.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (atBottom !== follow) setFollow(atBottom);
  };

  if (unsupported)
    return (
      <EmptyState title="Logs unavailable">
        {unsupported}
        {consoleUrl && (
          <>
            {" "}
            <a href={consoleUrl} target="_blank" rel="noopener noreferrer">
              Open the console ↗
            </a>
          </>
        )}
      </EmptyState>
    );

  const canOlder = mode === "seq" && entries.length > 0 && entries[0].seq > Math.max(1, oldest);

  return (
    <div className="logviewer">
      <div className="toolbar">
        <SearchInput value={query} onChange={setQuery} placeholder="Search messages…" />
        <Select
          label="Level"
          allLabel="All levels"
          value={filters.level}
          onChange={(level) => setFilters((f) => ({ ...f, level }))}
          options={LEVELS}
        />
        <Select
          label="Function"
          allLabel="All functions"
          value={filters.function}
          onChange={(fn) => setFilters((f) => ({ ...f, function: fn }))}
          options={functions}
        />
        <Select
          label="Source"
          allLabel="All sources"
          value={filters.source}
          onChange={(source) => setFilters((f) => ({ ...f, source }))}
          options={SOURCES}
        />
        <button type="button" className={paused ? "btn btn-primary" : "btn"} onClick={() => setPaused(!paused)}>
          {paused ? "▶ Resume" : "❚❚ Pause"}
        </button>
        <button type="button" className="btn" onClick={() => setEntries([])} title="Clear the view (server logs are kept)">
          Clear
        </button>
        {consoleUrl && (
          <a className="btn" href={consoleUrl} target="_blank" rel="noopener noreferrer" title="Open the provider console">
            Console ↗
          </a>
        )}
      </div>
      {error && <ErrorBanner message={`Could not read logs: ${error}`} />}
      <div className="logbox" ref={box} onScroll={onScroll} role="log" aria-live="polite">
        {canOlder && (
          <button type="button" className="btn btn-sm log-older" onClick={loadOlder} disabled={olderLoading}>
            {olderLoading ? "Loading…" : "Load older"}
          </button>
        )}
        {loading && <Spinner label="Loading logs…" />}
        {!loading && !entries.length && <div className="muted log-empty">No log entries yet.</div>}
        {entries.map((e) => (
          <div key={e.seq} className={`log-line log-${levelTone(e.level)}`}>
            <time className="log-ts">{formatTime(e.ts)}</time>
            <span className={`log-level lvl-${levelTone(e.level)}`}>{(e.level || "").slice(0, 5)}</span>
            <span className="log-src">
              {e.function || e.source}
              {typeof e.fields?.server === "string" || typeof e.fields?.replica === "string"
                ? ` · ${[e.fields?.server, e.fields?.replica].filter((v) => typeof v === "string").join("/")}`
                : ""}
            </span>
            <span className="log-msg">
              {e.message}
              {e.fields && Object.keys(e.fields).some((k) => k !== "server" && k !== "replica") && (
                <span className="log-fields">
                  {" "}
                  {JSON.stringify(
                    Object.fromEntries(Object.entries(e.fields).filter(([k]) => k !== "server" && k !== "replica")),
                  )}
                </span>
              )}
              {e.request_id && <span className="log-rid"> #{e.request_id.slice(0, 8)}</span>}
            </span>
          </div>
        ))}
      </div>
      <div className="log-status muted">
        <span>
          {entries.length} entries{paused ? " · paused" : " · live"}
          {mode === "time" ? " · cloud logs arrive with a few seconds' delay" : ""}
        </span>
        {!follow && (
          <button type="button" className="btn btn-sm" onClick={() => setFollow(true)}>
            ↓ Jump to latest
          </button>
        )}
      </div>
    </div>
  );
}
