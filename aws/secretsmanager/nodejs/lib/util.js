"use strict";
// Small helpers: logging, time, key sorting, constant-time comparison, hashes.

const crypto = require("crypto");

function log(...parts) {
  console.log(new Date().toISOString().replace(/\.\d+Z$/, "+00:00"), ...parts);
}

const now = () => Math.round(Date.now()) / 1000;
const today = () => Math.floor(Date.now() / 1000 / 86400) * 86400;
const has = (obj, key) => obj[key] !== undefined && obj[key] !== null;

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = sortKeys(value[key]);
    return out;
  }
  return value;
}

function byCodePoint(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

const hmac = (key, text) => crypto.createHmac("sha256", key).update(text, "utf8").digest();
const sha256 = (data) => crypto.createHash("sha256").update(data).digest("hex");

function safeEqual(a, b) {
  const x = Buffer.from(String(a), "utf8");
  const y = Buffer.from(String(b), "utf8");
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

module.exports = { log, now, today, has, sortKeys, byCodePoint, hmac, sha256, safeEqual };
