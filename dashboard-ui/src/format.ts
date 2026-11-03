export function safeUrl(value: unknown): string | null {
  return typeof value === "string" && /^https?:\/\//i.test(value) ? value : null;
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : d.toLocaleString();
}

export function formatTime(value?: string | null): string {
  if (!value) return "";
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : d.toLocaleTimeString(undefined, { hour12: false });
}

export function formatDuration(ms?: number | null): string {
  if (ms === null || ms === undefined || isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 2 : 1)} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${Math.round(s % 60)}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function relative(value?: string | null): string {
  if (!value) return "—";
  const t = new Date(value).getTime();
  if (isNaN(t)) return value;
  const diff = (Date.now() - t) / 1000;
  if (diff < 45) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  return `${Math.round(diff / 86400)} d ago`;
}

export type Tone = "ok" | "warn" | "err" | "off" | "info" | "accent";

export function statusTone(status?: string | null): Tone {
  switch ((status || "").toUpperCase()) {
    case "SUCCEEDED":
    case "DEPLOYED":
      return "ok";
    case "RUNNING":
      return "info";
    case "FAILED":
    case "TIMED_OUT":
      return "err";
    case "ABORTED":
    case "CANCELLED":
    case "REMOVED":
      return "off";
    default:
      return "warn";
  }
}

export function levelTone(level?: string): Tone {
  switch ((level || "").toUpperCase()) {
    case "ERROR":
    case "CRITICAL":
      return "err";
    case "WARNING":
      return "warn";
    case "DEBUG":
      return "off";
    default:
      return "info";
  }
}
