"use strict";
/** Small helpers shared by the runtime modules (no dependencies). */

/** Python `datetime.isoformat()` of an aware UTC datetime: `2026-01-02T03:04:05.123000+00:00`. */
function isoformat(date) {
  const d = date instanceof Date ? date : new Date(date);
  const iso = d.toISOString(); // 2026-01-02T03:04:05.123Z
  return `${iso.slice(0, 19)}.${iso.slice(20, 23)}000+00:00`;
}

/** Python `round(x, 2)` for durations. */
function round2(x) {
  return Math.round(x * 100) / 100;
}

/** Milliseconds from a monotonic clock. */
function nowMs() {
  if (typeof process !== "undefined" && process.hrtime && typeof process.hrtime.bigint === "function") {
    return Number(process.hrtime.bigint()) / 1e6;
  }
  if (typeof performance !== "undefined" && typeof performance.now === "function") return performance.now();
  return Date.now();
}

/**
 * A Node.js built-in (or a file, with `throws`), or null where there is none
 * (Cloudflare Workers). The require is indirect so bundlers don't try to inline it.
 */
function nodeModule(name, throws = false) {
  const req = typeof require === "function" ? require : null;
  if (!req) {
    if (throws) throw new Error(`cannot load ${name}: require() is not available`);
    return null;
  }
  if (throws) return req(name);
  try {
    return req(name);
  } catch (err) {
    return null;
  }
}

function webCrypto() {
  return typeof globalThis !== "undefined" && globalThis.crypto && typeof globalThis.crypto.getRandomValues === "function"
    ? globalThis.crypto
    : null;
}

/** Random UUID v4 (Web Crypto where available, else Node's crypto). */
function randomUUID() {
  const web = webCrypto();
  if (web && typeof web.randomUUID === "function") return web.randomUUID();
  return nodeModule("crypto", true).randomUUID();
}

/** `n` random hex characters. */
function randomHex(n) {
  const bytes = new Uint8Array(Math.ceil(n / 2));
  const web = webCrypto();
  if (web) web.getRandomValues(bytes);
  else bytes.set(nodeModule("crypto", true).randomBytes(bytes.length));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").slice(0, n);
}

/** `process.env`, or an empty object where `process` doesn't exist. */
function env() {
  return typeof process !== "undefined" && process.env ? process.env : {};
}

function isPlainObject(value) {
  if (value === null || typeof value !== "object") return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/** Deep equality for JSON-like values (Python `==` on dict / list / scalars). */
function deepEqual(a, b) {
  if (a === b) return true;
  if (typeof a === "number" && typeof b === "number") return a === b;
  if (Array.isArray(a)) {
    if (!Array.isArray(b) || a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) if (!deepEqual(a[i], b[i])) return false;
    return true;
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    for (const k of ka) if (!Object.prototype.hasOwnProperty.call(b, k) || !deepEqual(a[k], b[k])) return false;
    return true;
  }
  return false;
}

function deepCopy(value) {
  if (Array.isArray(value)) return value.map(deepCopy);
  if (isPlainObject(value)) {
    const out = {};
    for (const [k, v] of Object.entries(value)) out[k] = deepCopy(v);
    return out;
  }
  return value;
}

module.exports = { isoformat, round2, nowMs, nodeModule, env, randomUUID, randomHex, isPlainObject, deepEqual, deepCopy };
