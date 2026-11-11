// Formatting helpers. Secrets Manager dates are epoch seconds (floats).

const pad = (n) => String(n).padStart(2, "0");

/** "November 11, 2026, 14:05:09 (UTC+01:00)" like the AWS console, in the viewer's time zone. */
export function dateTime(seconds) {
  if (!seconds && seconds !== 0) return "-";
  const d = new Date(seconds * 1000);
  const offset = -d.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const tz = `UTC${sign}${pad(Math.floor(Math.abs(offset) / 60))}:${pad(Math.abs(offset) % 60)}`;
  const day = d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
  return `${day}, ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} (${tz})`;
}

/** The UTC date only (LastAccessedDate is rounded to the day, as on AWS). */
export function utcDate(seconds) {
  if (!seconds) return "-";
  const d = new Date(seconds * 1000);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** "3 minutes ago", "in 7 days". */
export function relative(seconds) {
  if (!seconds) return "";
  const diff = seconds - Date.now() / 1000;
  const abs = Math.abs(diff);
  const units = [["year", 31536000], ["month", 2592000], ["day", 86400], ["hour", 3600], ["minute", 60]];
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, size] of units) {
    if (abs >= size) return rtf.format(Math.round(diff / size), unit);
  }
  return rtf.format(Math.round(diff), "second");
}

export function truncate(text, max = 80) {
  const s = String(text || "");
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function shortId(id) {
  return id ? `${String(id).slice(0, 8)}…` : "";
}

/** A JSON object value (key/value secret), else null. */
export function parseObject(text) {
  if (typeof text !== "string" || !text.trim().startsWith("{")) return null;
  try {
    const v = JSON.parse(text);
    return v && typeof v === "object" && !Array.isArray(v) ? v : null;
  } catch {
    return null;
  }
}

export function stringify(value) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}
