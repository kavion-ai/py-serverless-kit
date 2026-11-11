"use strict";
// The web console: sign-in sessions (HttpOnly cookie + CSRF token, sign-in throttling) and its static files
// (ui/index.html and ui/assets/**).

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { CREDENTIALS, SESSION_TTL, UI_DIR, UI_PASSWORD } = require("./config");
const { safeEqual } = require("./util");

const sessions = new Map();
const failures = new Map();

function checkLogin(user, password) {
  if (UI_PASSWORD) return safeEqual(password, UI_PASSWORD);
  const known = Object.prototype.hasOwnProperty.call(CREDENTIALS, user);
  // Compare against a dummy for an unknown user, so the time is the same.
  return safeEqual(password, known ? CREDENTIALS[user] : "\0".repeat(32)) && known;
}

function throttled(ip) {
  const t = Date.now() / 1000;
  const recent = (failures.get(ip) || []).filter((x) => t - x < 300);
  failures.set(ip, recent);
  return recent.length >= 10;
}

function failed(ip) {
  failures.set(ip, [...(failures.get(ip) || []), Date.now() / 1000]);
}

function newSession(user) {
  const sid = crypto.randomBytes(32).toString("base64url");
  const csrf = crypto.randomBytes(24).toString("base64url");
  const t = Date.now() / 1000;
  for (const [key, s] of sessions) if (s.expires < t) sessions.delete(key);
  sessions.set(sid, { user, csrf, expires: t + SESSION_TTL });
  return [sid, csrf];
}

function sessionOf(cookieHeader) {
  for (const part of String(cookieHeader || "").split(";")) {
    const at = part.indexOf("=");
    if (at > 0 && part.slice(0, at).trim() === "sm_session") {
      const id = part.slice(at + 1).trim();
      const found = sessions.get(id);
      if (found && found.expires > Date.now() / 1000) return { ...found, id };
    }
  }
  return null;
}

// ----------------------------------------------------------------------------- static files

// The directory of server.js (the entry point), set by main(); the UI is looked up from there, not from lib/.
let serverDir = path.resolve(__dirname, "..");

function setServerDir(dir) {
  serverDir = dir;
}

/** SM_UI_DIR, else <server dir>/ui (the images), else <server dir>/../ui (the repository). */
function uiDir() {
  if (UI_DIR) return UI_DIR;
  for (const dir of [path.join(serverDir, "ui"), path.join(serverDir, "..", "ui")]) {
    if (fs.existsSync(path.join(dir, "index.html"))) return dir;
  }
  return path.join(serverDir, "ui");
}

const UI_CSP = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
  + "img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'";

const UI_HEADERS = {
  "Cache-Control": "no-store",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy": UI_CSP,
};

const MIME = {
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".json": "application/json",
  ".html": "text/html; charset=utf-8",
};

function uiHtml() {
  const file = path.join(uiDir(), "index.html");
  if (fs.existsSync(file)) return fs.readFileSync(file);
  return Buffer.from("<!doctype html><title>Secrets console</title><p>The console page (index.html) is missing.");
}

/** [body, content type] of /ui/assets/<rel>, or null when it is not a file under ui/assets. */
function uiAsset(rel) {
  let decoded;
  try {
    decoded = decodeURIComponent(rel);
  } catch {
    return null;
  }
  if (!decoded || decoded.includes("\\") || decoded.includes("\0")) return null;
  const segments = decoded.split("/");
  if (segments.some((s) => !s || s.startsWith("."))) return null;
  const root = path.join(uiDir(), "assets");
  let realRoot;
  let real;
  try {
    realRoot = fs.realpathSync(root);
    real = fs.realpathSync(path.join(root, ...segments));
  } catch {
    return null;
  }
  if (!real.startsWith(realRoot + path.sep)) return null;
  let stat;
  try {
    stat = fs.statSync(real);
  } catch {
    return null;
  }
  if (!stat.isFile()) return null;
  const ext = path.extname(real).toLowerCase();
  return [fs.readFileSync(real), MIME[ext] || "application/octet-stream"];
}

module.exports = {
  sessions, checkLogin, throttled, failed, newSession, sessionOf, setServerDir, uiDir, uiHtml, uiAsset, UI_HEADERS,
};
