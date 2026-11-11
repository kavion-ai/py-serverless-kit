"use strict";
// Python built-in semantics the two servers must agree on: int(), float(), str(), str.strip(), truthiness,
// dict.get(), code-point string order, bisect and json.dumps. (The Python server gets these from Python itself.)

class ValueError extends Error {}

const PY_WS = "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const STRIP_RE = new RegExp(`^[${PY_WS}]+|[${PY_WS}]+$`, "g");
const SPLIT_RE = new RegExp(`[${PY_WS}]+`);

/** str.strip() as Python does it (its whitespace set differs a little from String.prototype.trim). */
const pyStrip = (s) => String(s).replace(STRIP_RE, "");

/** str.split() without arguments. */
const pySplit = (s) => {
  const t = pyStrip(s);
  return t ? t.split(SPLIT_RE) : [];
};

/** bytes.strip(): ASCII whitespace only. */
const asciiStrip = (s) => s.replace(/^[ \t\n\r\x0b\x0c]+|[ \t\n\r\x0b\x0c]+$/g, "");

/** int() as Python parses it: surrounding whitespace, a sign and underscores between digits; else ValueError. */
function pyInt(value, base = 10) {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new ValueError("cannot convert float to integer");
    return Math.trunc(value);
  }
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value !== "string") throw new TypeError("int() argument must be a string or a number");
  let s = pyStrip(value);
  const re = base === 16 ? /^[+-]?(?:0[xX]_?)?[0-9a-fA-F](?:_?[0-9a-fA-F])*$/ : /^[+-]?[0-9](?:_?[0-9])*$/;
  if (!re.test(s)) throw new ValueError(`invalid literal for int() with base ${base}: '${value}'`);
  s = s.replace(/_/g, "");
  let negative = false;
  if (s[0] === "-" || s[0] === "+") {
    negative = s[0] === "-";
    s = s.slice(1);
  }
  if (base === 16) s = s.replace(/^0[xX]/, "");
  const n = parseInt(s, base);
  return negative ? -n : n;
}

function pyFloat(value) {
  const n = Number(pyStrip(value));
  if (Number.isNaN(n)) throw new ValueError(`could not convert string to float: '${value}'`);
  return n;
}

/** str() of a JSON value, as Python prints it. */
function pyStr(value) {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "object") return pyDumps(value);
  return String(value);
}

/** Python truthiness of a JSON value. */
function truthy(value) {
  if (value === null || value === undefined || value === false || value === 0 || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

const own = (obj, key) => obj !== null && typeof obj === "object" && Object.prototype.hasOwnProperty.call(obj, key);

/** dict.get(key, default). */
const g = (obj, key, def = undefined) => (own(obj, key) ? obj[key] : def);

/** params.get(): like dict.get, but a body that is not an object fails (Python's AttributeError, a 500). */
function pget(p, key, def = undefined) {
  if (p === null || typeof p !== "object" || Array.isArray(p)) throw new TypeError("the parameters are not an object");
  return g(p, key, def);
}

const nullObj = () => Object.create(null);

/** Python's string order (code points), which differs from UTF-16 order above U+FFFF. */
function cmpStr(a, b) {
  if (a === b) return 0;
  const n = Math.min(a.length, b.length);
  let i = 0;
  while (i < n && a.charCodeAt(i) === b.charCodeAt(i)) i++;
  if (i === n) return a.length - b.length;
  let x = a.charCodeAt(i);
  let y = b.charCodeAt(i);
  if (x >= 0xd800 && x <= 0xdfff) x += 0x2800;
  if (y >= 0xd800 && y <= 0xdfff) y += 0x2800;
  return x - y;
}

function bisectLeft(list, value) {
  let lo = 0;
  let hi = list.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cmpStr(list[mid], value) < 0) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function bisectRight(list, value) {
  let lo = 0;
  let hi = list.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cmpStr(value, list[mid]) < 0) hi = mid;
    else lo = mid + 1;
  }
  return lo;
}

const asciiJson = (s) =>
  JSON.stringify(s).replace(/[\u007f-￿]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`);

/** json.dumps: Python's separators (", " / ": ", or compact), ensure_ascii, optionally sort_keys. */
function pyDumps(value, sortKeys = false, compact = false) {
  const item = compact ? "," : ", ";
  const kv = compact ? ":" : ": ";
  const enc = (v) => {
    if (v === null || v === undefined) return "null";
    if (v === true) return "true";
    if (v === false) return "false";
    if (typeof v === "number") {
      if (Number.isFinite(v)) return JSON.stringify(v);
      return Number.isNaN(v) ? "NaN" : v > 0 ? "Infinity" : "-Infinity";
    }
    if (typeof v === "string") return asciiJson(v);
    if (Array.isArray(v)) return `[${v.map(enc).join(item)}]`;
    if (v instanceof Map) return enc(Object.fromEntries(v));
    const keys = Object.keys(v).filter((k) => v[k] !== undefined);
    if (sortKeys) keys.sort(cmpStr);
    return `{${keys.map((k) => asciiJson(k) + kv + enc(v[k])).join(item)}}`;
  };
  return enc(value);
}

const isDict = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const asList = (value) => (Array.isArray(value) ? value : value !== null && value !== undefined ? [value] : []);
const pyLen = (s) => [...s].length;

module.exports = {
  g, own, ValueError, pyStrip, pyStr, pySplit, asciiStrip, pyInt, pyFloat, pyDumps, truthy, pget, nullObj, cmpStr,
  bisectLeft, bisectRight, isDict, asList, pyLen,
};
