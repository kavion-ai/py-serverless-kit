import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "./api";
import type { Job, JobLine, JobStatus } from "./types";

export interface JobView {
  id: string | null;
  command: string;
  status: JobStatus | "idle";
  exitCode: number | null;
  lines: JobLine[];
  error: string | null;
}

const MAX_LINES = 5000;

/** Poll a studio job and accumulate its output until it finishes. */
export function useJob(id: string | null, interval = 700): JobView {
  const [view, setView] = useState<JobView>({ id: null, command: "", status: "idle", exitCode: null, lines: [], error: null });
  const cursor = useRef(0);

  useEffect(() => {
    if (!id) {
      setView({ id: null, command: "", status: "idle", exitCode: null, lines: [], error: null });
      return undefined;
    }
    cursor.current = 0;
    setView({ id, command: "", status: "running", exitCode: null, lines: [], error: null });
    let live = true;
    let timer = 0;
    let failures = 0;
    const tick = async () => {
      try {
        const job: Job = await api.job(id, cursor.current);
        if (!live) return;
        failures = 0;
        cursor.current = job.next ?? cursor.current;
        setView((v) => ({
          id,
          command: job.command,
          status: job.status,
          exitCode: job.exit_code ?? null,
          lines: [...v.lines, ...(job.lines || [])].slice(-MAX_LINES),
          error: null,
        }));
        if (job.status === "running") timer = window.setTimeout(tick, document.hidden ? interval * 4 : interval);
      } catch (exc) {
        if (!live) return;
        failures++;
        setView((v) => ({ ...v, error: errorMessage(exc) }));
        if (failures < 20) timer = window.setTimeout(tick, Math.min(10000, interval * 2 ** failures));
      }
    };
    void tick();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [id, interval]);

  return view;
}
