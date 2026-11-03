import { useCallback, useEffect, useRef, useState } from "react";

export interface PollState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

/**
 * Fetch `load` now and then every `interval` ms while `enabled`.
 * Errors back off exponentially (up to 8x); polling pauses while the tab is hidden.
 * `interval` 0 loads once.
 */
export function usePolling<T>(load: () => Promise<T>, interval: number, enabled: boolean, deps: unknown[]): PollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    setData(null);
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    let failures = 0;

    const run = async () => {
      if (cancelled) return;
      if (document.visibilityState === "hidden" && interval > 0) {
        timer = window.setTimeout(run, interval);
        return;
      }
      setLoading(true);
      try {
        const value = await loadRef.current();
        if (cancelled) return;
        setData(value);
        setError(null);
        failures = 0;
      } catch (err) {
        if (cancelled) return;
        failures += 1;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
      if (!cancelled && interval > 0) {
        timer = window.setTimeout(run, interval * Math.min(8, 2 ** Math.max(0, failures - 1)));
      }
    };
    const onVisible = () => {
      if (document.visibilityState === "visible" && interval > 0) {
        window.clearTimeout(timer);
        run();
      }
    };
    run();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, interval, tick, ...deps]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, refresh };
}

export function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable (private mode, file://) */
  }
}

/** Value stored in the URL hash, so views survive a reload and can be linked. */
export function useHashRoute(): [string, (next: string) => void] {
  const read = () => decodeURIComponent(window.location.hash.replace(/^#\/?/, ""));
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((next: string) => {
    window.location.hash = next ? `/${next}` : "";
  }, []);
  return [route, navigate];
}
