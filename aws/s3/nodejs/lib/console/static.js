"use strict";
// The console's static files: the page shell (/ui/) and /ui/assets/<path>. Neither needs a session.

const fs = require("fs");
const path = require("path");

const { UI_DIR } = require("../config");
const { S3Error } = require("../errors");
const { unquote } = require("../util");
const { Response } = require("../http");

const SERVER_DIR = path.resolve(__dirname, "..", ".."); // the folder holding server.js
/** Headers of the console page. Every script is a file under assets/js, so no inline script may run. */
const UI_HEADERS = {
  "Cache-Control": "no-store",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
    "connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; " +
    "frame-src 'self' blob:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
};
const TYPES = {
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".json": "application/json",
};

/** A regular file's size, or -1. */
function fileSize(file) {
  try {
    const st = fs.statSync(file);
    return st.isFile() ? st.size : -1;
  } catch {
    return -1;
  }
}

/** S3_UI_DIR, else ui next to server.js (the images), else ../ui (the repository). */
function uiDir() {
  if (UI_DIR) return UI_DIR;
  const beside = path.join(SERVER_DIR, "ui");
  try {
    if (fs.statSync(beside).isDirectory()) return beside;
  } catch {
    // not there: the repository layout
  }
  return path.join(SERVER_DIR, "..", "ui");
}

/** GET /ui/: the console page. */
function indexPage() {
  const page = path.join(uiDir(), "index.html");
  const body = fileSize(page) >= 0
    ? fs.readFileSync(page)
    : Buffer.from("<!doctype html><title>S3 console</title><p>The console page (index.html) is missing.");
  return new Response(200, body, UI_HEADERS, "text/html; charset=utf-8");
}

/** A file under ui/assets/; `rawPath` is the URL path after /ui/assets/, still percent-encoded. */
function asset(rawPath) {
  const rel = unquote(rawPath);
  const parts = rel.split("/");
  const unsafe = ["\\", "\0", ":"].some((c) => rel.includes(c)) || parts.some((p) => !p || p.startsWith("."));
  const file = path.join(uiDir(), "assets", ...parts);
  const size = unsafe ? -1 : fileSize(file);
  if (size < 0) throw new S3Error("NotFound", "Not found.", 404);
  const headers = { "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff" };
  const ctype = TYPES[path.extname(file).toLowerCase()] || "application/octet-stream";
  return new Response(200, Buffer.alloc(0), headers, ctype, file, 0, size);
}

module.exports = { indexPage, asset };
