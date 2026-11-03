import type { HistoryEvent } from "../types";
import { formatTime } from "../format";

const SKIP = new Set(["ts", "state", "type", "event"]);

function tone(event?: string): string {
  switch (event) {
    case "caught":
    case "retry":
      return "warn";
    case "fail":
      return "err";
    case "exit":
      return "ok";
    default:
      return "info";
  }
}

/** Execution history, oldest first. The last `enter` of `current` is highlighted while running. */
export function Timeline({ events, current, running }: { events: HistoryEvent[]; current?: string | null; running?: boolean }) {
  if (!events.length) return <p className="muted">No history recorded yet.</p>;
  let highlight = -1;
  if (running && current) {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].state === current) {
        highlight = i;
        break;
      }
    }
  }
  return (
    <ol className="timeline">
      {events.map((e, i) => {
        const extra = Object.entries(e).filter(([k, v]) => !SKIP.has(k) && v !== undefined && v !== null);
        return (
          <li key={i} className={`tl-item tl-${tone(e.event)}${i === highlight ? " tl-current" : ""}`}>
            <span className="tl-dot" aria-hidden="true" />
            <div className="tl-main">
              <div className="tl-title">
                <b>{e.state || "—"}</b>
                {e.type && <span className="chip">{e.type}</span>}
                {e.event && <span className="muted">{e.event}</span>}
                {i === highlight && <span className="badge badge-info">running</span>}
              </div>
              {extra.length > 0 && (
                <div className="tl-extra mono">
                  {extra.map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join("  ")}
                </div>
              )}
            </div>
            <time className="tl-time mono">{formatTime(e.ts)}</time>
          </li>
        );
      })}
    </ol>
  );
}
