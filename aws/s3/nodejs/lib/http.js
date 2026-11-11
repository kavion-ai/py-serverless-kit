"use strict";
// HTTP: Request (path, query, headers, body), Response, error responses, sending, and dispatch() of one request.

const crypto = require("crypto");
const fs = require("fs");

const { nullObj, pyDumps, pyInt, pyStrip } = require("./py");
const { S3Error } = require("./errors");
const { MAX_OBJECT, MAX_XML, VERSION } = require("./config");
const { doc, log, splitQuery, x } = require("./util");
const { getStore } = require("./store");
const { Auth, receive } = require("./sigv4");
const { corsMatch } = require("./cors");

/** The request body as sent (Node has already removed HTTP chunked transfer coding), read on demand. */
class Raw {
  constructor(req, length, chunked) {
    this.req = req;
    this.iter = null;
    this.done = !chunked && !length;
    this.pieces = [];
    this.len = 0;
  }

  async fill() {
    if (this.done) return false;
    if (!this.iter) this.iter = this.req[Symbol.asyncIterator]();
    let r;
    try {
      r = await this.iter.next();
    } catch {
      this.done = true;
      throw new S3Error("IncompleteBody", "You did not provide the number of bytes specified by the Content-Length HTTP header");
    }
    if (r.done) {
      this.done = true;
      if (!this.req.complete) {
        throw new S3Error("IncompleteBody", "You did not provide the number of bytes specified by the Content-Length HTTP header");
      }
      return false;
    }
    if (r.value.length) {
      this.pieces.push(r.value);
      this.len += r.value.length;
    }
    return true;
  }

  take(n) {
    n = Math.max(0, Math.min(n, this.len));
    if (!n) return Buffer.alloc(0);
    const all = this.pieces.length === 1 ? this.pieces[0] : Buffer.concat(this.pieces);
    const out = all.subarray(0, n);
    const rest = all.subarray(n);
    this.pieces = rest.length ? [rest] : [];
    this.len = rest.length;
    return out;
  }

  async read(n) {
    while (this.len < n && !this.done) await this.fill();
    return this.take(n);
  }

  async readline(limit = 8192) {
    for (;;) {
      if (this.pieces.length > 1) this.pieces = [Buffer.concat(this.pieces)];
      const idx = this.pieces.length ? this.pieces[0].indexOf(10) : -1;
      if (idx >= 0) return this.take(idx + 1);
      if (this.done || this.len >= limit) return this.take(this.len);
      await this.fill();
    }
  }

  async *chunks() {
    if (this.len) yield this.take(this.len);
    while (!this.done) if ((await this.fill()) && this.len) yield this.take(this.len);
  }

  async drain() {
    // eslint-disable-next-line no-unused-vars
    for await (const _ of this.chunks());
  }
}

function lowerHeaders(nreq) {
  const out = nullObj();
  const raw = nreq.rawHeaders;
  const names = [];
  const values = nullObj();
  for (let i = 0; i < raw.length; i += 2) {
    const low = raw[i].toLowerCase();
    if (values[low] === undefined) {
      values[low] = [];
      names.push(low);
    }
    values[low].push(pyStrip(raw[i + 1]));
  }
  for (const name of names) out[name] = values[name].join(",");
  return out;
}

/** urllib.parse.urlsplit's path and query of a request target. */
function splitTarget(target) {
  let rest = target;
  const scheme = /^[A-Za-z][A-Za-z0-9+.-]*:/.exec(rest);
  if (scheme && rest.slice(scheme[0].length, scheme[0].length + 2) === "//") rest = rest.slice(scheme[0].length);
  if (rest.startsWith("//")) {
    const m = /^\/\/[^/?#]*/.exec(rest);
    rest = rest.slice(m[0].length);
  }
  const hash = rest.indexOf("#");
  if (hash >= 0) rest = rest.slice(0, hash);
  const qi = rest.indexOf("?");
  return qi < 0 ? [rest, ""] : [rest.slice(0, qi), rest.slice(qi + 1)];
}

class Request {
  constructor(nreq) {
    this.nreq = nreq;
    this.method = nreq.method;
    const [rawPath, rawQuery] = splitTarget(nreq.url || "/");
    this.raw_path = rawPath || "/";
    this.raw_query = rawQuery;
    this.pairs = splitQuery(rawQuery);
    this.q = nullObj();
    for (const [k, v] of this.pairs) this.q[k] = v;
    this.headers = lowerHeaders(nreq);
    this.host = this.headers.host || "";
    this.bucket = "";
    this.key = "";
    this.vhost = "";
    this.auth = new Auth(null);
    this.ip = (nreq.socket && nreq.socket.remoteAddress) || "";
    const length = this.headers["content-length"];
    const chunked = (this.headers["transfer-encoding"] || "").toLowerCase().includes("chunked");
    let n = 0;
    if (length) {
      try {
        n = pyInt(length);
      } catch {
        throw new S3Error("InvalidArgument", "Content-Length is not valid.");
      }
    }
    this.raw = new Raw(nreq, n, chunked);
    this.consumed = !n && !chunked;
  }

  get who() {
    return this.auth.principal;
  }

  async smallBody(limit = MAX_XML) {
    this.consumed = true;
    const [, data] = await receive(this.raw, this.headers, this.auth, limit, "", "", false);
    return data;
  }

  async payload(alg, expected, limit = MAX_OBJECT) {
    this.consumed = true;
    const [received] = await receive(this.raw, this.headers, this.auth, limit, alg, expected);
    return received;
  }
}

class Response {
  constructor(status = 200, body = Buffer.alloc(0), headers = {}, ctype = "application/xml", file = null, start = 0, length = 0) {
    this.status = status;
    this.body = Buffer.isBuffer(body) ? body : Buffer.from(body, "utf8");
    this.headers = { ...headers };
    this.ctype = ctype;
    this.file = file;
    this.start = start;
    this.length = length;
  }
}

const xmlResponse = (root, inner, status = 200, headers = {}) => new Response(status, doc(root, inner), headers);

const jsonResponse = (data, headers = { "Cache-Control": "no-store" }, status = 200) =>
  new Response(status, Buffer.from(pyDumps(data), "utf8"), headers, "application/json");

const requestId = () => crypto.randomBytes(8).toString("hex").toUpperCase();

function errorResponse(exc, req, method) {
  const resource = req ? req.raw_path : "/";
  if (resource === "/ui" || resource.startsWith("/ui/")) {
    // The console reads JSON errors.
    return jsonResponse({ code: exc.code, message: exc.message }, { "Cache-Control": "no-store" }, exc.status);
  }
  const extra = Object.entries(exc.extra).filter(([, v]) => v).map(([k, v]) => x(k, v)).join("");
  const body = exc.status === 304 || method === "HEAD"
    ? Buffer.alloc(0)
    : Buffer.from(`<?xml version="1.0" encoding="UTF-8"?>\n<Error>${x("Code", exc.code)}${x("Message", exc.message)}` +
      `${extra}${x("Resource", resource)}${x("RequestId", requestId())}</Error>`, "utf8");
  const resp = new Response(exc.status, body, exc.headers);
  if (method === "HEAD" && exc.status !== 304 && resp.headers["Content-Type"] === undefined) resp.headers["Content-Type"] = "application/xml";
  return resp;
}

function sendResponse(nreq, res, resp, req) {
  const headers = { Server: `pskit-s3/${VERSION}`, "x-amz-request-id": requestId(), "x-amz-id-2": crypto.randomBytes(24).toString("base64") };
  Object.assign(headers, resp.headers);
  // The body was not read to its end (refused early, or an error mid-body): the rest of it must not be taken for
  // the next request on this connection.
  if (req && (!req.consumed || !req.raw.done)) headers.Connection = "close";
  const length = resp.file !== null ? resp.length : resp.body.length;
  if (resp.status !== 304 && resp.status !== 204) {
    if ((resp.body.length || resp.file !== null || resp.headers["Content-Type"] !== undefined) && headers["Content-Type"] === undefined) {
      headers["Content-Type"] = resp.ctype;
    }
    headers["Content-Length"] = String(length);
  } else if (resp.status === 204) {
    delete headers["Content-Length"];
  }
  try {
    res.writeHead(resp.status, headers);
  } catch (err) {
    // A header value Node refuses (Python's http.server fails the same way): drop the connection.
    log("error:", String(err.message || err));
    res.destroy();
    return;
  }
  if (nreq.method === "HEAD" || resp.status === 204 || resp.status === 304) {
    res.end();
    return;
  }
  if (resp.file !== null) {
    if (resp.length <= 0) {
      res.end();
      return;
    }
    const stream = fs.createReadStream(resp.file, { start: resp.start, end: resp.start + resp.length - 1, highWaterMark: 256 * 1024 });
    stream.on("error", () => res.destroy());
    res.on("close", () => stream.destroy());
    stream.pipe(res);
  } else {
    res.end(resp.body);
  }
}

const METHODS = new Set(["GET", "HEAD", "PUT", "POST", "DELETE", "OPTIONS"]);

/** The answer Python's http.server gives a method it has no handler for. */
function unsupportedMethod(nreq, res) {
  const body = Buffer.from("<!DOCTYPE HTML>\n<html lang=\"en\">\n    <head>\n        <meta charset=\"utf-8\">\n" +
    "        <title>Error response</title>\n    </head>\n    <body>\n        <h1>Error response</h1>\n" +
    "        <p>Error code: 501</p>\n" +
    `        <p>Message: Unsupported method ('${nreq.method.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}').</p>\n` +
    "        <p>Error code explanation: 501 - Server does not support this operation.</p>\n    </body>\n</html>\n", "utf8");
  res.writeHead(501, { Server: `pskit-s3/${VERSION}`, Connection: "close", "Content-Type": "text/html;charset=utf-8", "Content-Length": String(body.length) });
  res.end(body);
}

/** Answer one HTTP request: `route(req)` makes the Response (main passes routes/index's route). */
async function dispatch(nreq, res, route) {
  if (!METHODS.has(nreq.method)) {
    unsupportedMethod(nreq, res);
    return;
  }
  let req = null;
  let resp;
  try {
    req = new Request(nreq);
    resp = await route(req);
  } catch (err) {
    if (err instanceof S3Error) {
      resp = errorResponse(err, req, nreq.method);
    } else {
      log("error:", err && err.stack ? err.stack : String(err));
      resp = errorResponse(new S3Error("InternalError", "We encountered an internal error. Please try again.", 500), req, nreq.method);
    }
  }
  if (req && req.bucket && req.headers.origin !== undefined && req.method !== "OPTIONS") {
    const bucket = getStore().buckets.get(req.bucket);
    if (bucket) {
      const found = corsMatch(bucket, req.headers.origin, req.method, []);
      if (found) {
        delete found["Access-Control-Allow-Headers"];
        Object.assign(resp.headers, found);
      }
    }
  }
  sendResponse(nreq, res, resp, req);
}

module.exports = { Response, xmlResponse, jsonResponse, dispatch };
