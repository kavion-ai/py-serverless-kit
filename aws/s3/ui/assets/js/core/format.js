// Formatting helpers: sizes, dates, names, storage classes.

export function formatBytes(n) {
  if (n === undefined || n === null || n === "") return "-";
  let v = Number(n);
  if (!Number.isFinite(v)) return "-";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  const text = i === 0 ? String(v) : v.toFixed(v < 10 ? 1 : 0);
  return `${text} ${units[i]}`;
}

function offset(date) {
  const minutes = -date.getTimezoneOffset();
  const sign = minutes >= 0 ? "+" : "-";
  const abs = Math.abs(minutes);
  return `UTC${sign}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`;
}

/** "November 11, 2026, 14:03:12 (UTC+01:00)", like the AWS console. */
export function formatDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const date = d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  return `${date}, ${time} (${offset(d)})`;
}

export function plural(n, word, many) {
  return `${n} ${n === 1 ? word : many || word + "s"}`;
}

/** The last path segment of a key ("a/b/c.txt" -> "c.txt", "a/b/" -> "b"). */
export function baseName(key) {
  const trimmed = String(key || "").replace(/\/+$/, "");
  return trimmed.split("/").pop() || key;
}

/** The folder part of a key ("a/b/c.txt" -> "a/b/"). */
export function parentPrefix(key) {
  const trimmed = String(key || "").replace(/\/+$/, "");
  const i = trimmed.lastIndexOf("/");
  return i < 0 ? "" : trimmed.slice(0, i + 1);
}

/** The type column of the objects table: the extension, "Folder" or "-". */
export function fileType(key) {
  if (String(key).endsWith("/")) return "Folder";
  const name = baseName(key);
  const i = name.lastIndexOf(".");
  return i > 0 && i < name.length - 1 ? name.slice(i + 1).toLowerCase() : "-";
}

export const STORAGE_CLASSES = [
  { value: "STANDARD", label: "Standard", description: "Frequently accessed data (more than once a month) with milliseconds access." },
  { value: "INTELLIGENT_TIERING", label: "Intelligent-Tiering", description: "Data with changing or unknown access patterns." },
  { value: "STANDARD_IA", label: "Standard-IA", description: "Infrequently accessed data (once a month) with milliseconds access." },
  { value: "ONEZONE_IA", label: "One Zone-IA", description: "Recreatable, infrequently accessed data (once a month) stored in a single zone." },
  { value: "GLACIER_IR", label: "Glacier Instant Retrieval", description: "Long-lived archive data accessed once a quarter with instant retrieval in milliseconds." },
  { value: "GLACIER", label: "Glacier Flexible Retrieval", description: "Long-lived archive data accessed once a year; must be restored before it can be read." },
  { value: "DEEP_ARCHIVE", label: "Glacier Deep Archive", description: "Long-lived archive data accessed less than once a year; must be restored before it can be read." },
  { value: "REDUCED_REDUNDANCY", label: "Reduced redundancy", description: "Noncritical, frequently accessed data (not recommended)." },
];

export const ARCHIVED_CLASSES = ["GLACIER", "DEEP_ARCHIVE"];

export function storageClassLabel(value) {
  const found = STORAGE_CLASSES.find((c) => c.value === value);
  return found ? found.label : value || "Standard";
}

/** "3 days", "1 hour 30 minutes" */
export function durationText(seconds) {
  const parts = [];
  let s = Math.round(seconds);
  for (const [size, word] of [[86400, "day"], [3600, "hour"], [60, "minute"], [1, "second"]]) {
    if (s >= size) {
      const n = Math.floor(s / size);
      parts.push(plural(n, word));
      s -= n * size;
    }
  }
  return parts.slice(0, 2).join(" ") || "0 seconds";
}
