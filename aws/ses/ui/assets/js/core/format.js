// Formatting helpers. SES console timestamps are epoch seconds (floats).

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

/** 1536 -> "1.5 KB". */
export function bytes(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  const units = ["KB", "MB", "GB"];
  let x = v / 1024;
  let u = 0;
  while (x >= 1024 && u < units.length - 1) {
    x /= 1024;
    u += 1;
  }
  return `${x >= 10 ? Math.round(x) : x.toFixed(1)} ${units[u]}`;
}

/** 12345.0 -> "12,345". */
export function number(n) {
  return Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** "Nov 11, 14:05" (short, for tables). */
export function shortDate(seconds) {
  if (!seconds) return "-";
  const d = new Date(seconds * 1000);
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}
