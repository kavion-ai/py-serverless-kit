import { useEffect, useRef, useState } from "react";
import type { JobView } from "../jobs";
import { stripAnsi } from "../util";

/** Terminal-like output of a studio job. */
export function JobConsole({ job, emptyText = "Output appears here.", onCancel }: { job: JobView; emptyText?: string; onCancel?: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [job.lines, follow]);
  const statusText =
    job.status === "idle"
      ? ""
      : job.status === "running"
        ? "running…"
        : `${job.status}${job.exitCode !== null && job.exitCode !== undefined ? ` (exit ${job.exitCode})` : ""}`;
  return (
    <div className="console-wrap">
      <div className="console-bar">
        <span className={`console-status cs-${job.status}`}>
          {job.status === "running" && <span className="spinner spinner-sm" aria-hidden="true" />}
          {job.command ? <code className="mono">pskit {job.command}</code> : null} {statusText}
        </span>
        <span className="grow" />
        <label className="check small">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow
        </label>
        {onCancel && job.status === "running" && (
          <button type="button" className="btn btn-sm btn-danger" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      <div
        className="console"
        ref={box}
        role="log"
        aria-live="polite"
        onScroll={(e) => {
          const el = e.currentTarget;
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
          if (atBottom !== follow) setFollow(atBottom);
        }}
      >
        {!job.lines.length && <div className="console-empty">{job.error || emptyText}</div>}
        {job.lines.map((l) => (
          <div key={l.seq} className={l.stream === "stderr" ? "console-line console-err" : "console-line"}>
            {stripAnsi(l.text)}
          </div>
        ))}
        {job.error && job.lines.length > 0 && <div className="console-line console-err">⚠ {job.error}</div>}
      </div>
    </div>
  );
}
