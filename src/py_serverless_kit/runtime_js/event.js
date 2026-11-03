"use strict";
/**
 * Provider-neutral event model (port of runtime/event.py).
 *
 * Every adapter converts its native payload into an `Event`, so a handler
 * written against this module runs unchanged on any supported cloud.
 */

const { BadRequest } = require("./errors");
const { isoformat } = require("./util");

const EventType = Object.freeze({
  HTTP: "http",
  SCHEDULE: "schedule",
  QUEUE: "queue",
  STORAGE: "storage",
  TOPIC: "topic",
  INVOKE: "invoke",
  WORKFLOW: "workflow",
  SMTP: "smtp",
  ALL: Object.freeze(["http", "schedule", "queue", "storage", "topic", "invoke", "workflow", "smtp"]),
});

const MISSING = Symbol("missing");

/** Case-insensitive, read-only headers. Multi-value headers are joined with ", ". */
class Headers {
  /** @param {Record<string, any>|Array<[string, any]>|Headers|null} [raw] */
  constructor(raw) {
    this._data = new Map();
    let items = [];
    if (raw instanceof Headers) items = Array.from(raw._data.entries());
    else if (Array.isArray(raw)) items = raw;
    else if (raw && typeof raw === "object") items = Object.entries(raw);
    for (const [key, value0] of items) {
      if (value0 === null || value0 === undefined) continue;
      const value = Array.isArray(value0) ? value0.map(String).join(", ") : String(value0);
      const k = String(key).toLowerCase();
      this._data.set(k, this._data.has(k) ? `${this._data.get(k)}, ${value}` : value);
    }
  }

  get(key, fallback = undefined) {
    const k = String(key).toLowerCase();
    return this._data.has(k) ? this._data.get(k) : fallback;
  }

  has(key) {
    return this._data.has(String(key).toLowerCase());
  }

  keys() {
    return this._data.keys();
  }

  values() {
    return this._data.values();
  }

  entries() {
    return this._data.entries();
  }

  [Symbol.iterator]() {
    return this._data.entries();
  }

  get size() {
    return this._data.size;
  }

  toObject() {
    return Object.fromEntries(this._data);
  }

  toJSON() {
    return this.toObject();
  }
}

function decodeJson(raw, what) {
  const text = Buffer.isBuffer(raw) ? raw.toString("utf8") : String(raw);
  if (text === "") throw new BadRequest(`${what} is empty, expected JSON`);
  try {
    return JSON.parse(text);
  } catch (err) {
    throw new BadRequest(`${what} is not valid JSON`, { details: String(err.message) });
  }
}

function parseCookies(header) {
  const cookies = {};
  if (!header) return cookies;
  for (const part of String(header).split(";")) {
    const idx = part.indexOf("=");
    if (idx >= 0) cookies[part.slice(0, idx).trim()] = part.slice(idx + 1);
  }
  return cookies;
}

function toBuffer(body) {
  if (body === null || body === undefined) return Buffer.alloc(0);
  if (Buffer.isBuffer(body)) return body;
  if (body instanceof Uint8Array) return Buffer.from(body);
  if (typeof body === "string") return Buffer.from(body, "utf8");
  return Buffer.from(JSON.stringify(body), "utf8");
}

class HttpRequest {
  /**
   * @param {{method?: string, path?: string, headers?: any, query?: Record<string,string>,
   *          multiQuery?: Record<string,string[]>, pathParams?: Record<string,string>,
   *          body?: Buffer|string|null, sourceIp?: string|null, route?: string|null}} [init]
   */
  constructor(init = {}) {
    this.method = String(init.method || "GET").toUpperCase();
    this.path = init.path || "/";
    this.headers = init.headers instanceof Headers ? init.headers : new Headers(init.headers);
    this.query = Object.assign({}, init.query || {});
    this.multiQuery = Object.assign({}, init.multiQuery || init.multi_query || {});
    this.pathParams = Object.assign({}, init.pathParams || init.path_params || {});
    this.body = toBuffer(init.body);
    this.sourceIp = init.sourceIp || init.source_ip || null;
    this.route = init.route || null;
    if (Object.keys(this.query).length && !Object.keys(this.multiQuery).length) {
      for (const [k, v] of Object.entries(this.query)) this.multiQuery[k] = [v];
    }
  }

  get contentType() {
    return String(this.headers.get("content-type", "")).split(";")[0].trim().toLowerCase();
  }

  get cookies() {
    return parseCookies(this.headers.get("cookie"));
  }

  text(encoding = "utf8") {
    return this.body.toString(encoding);
  }

  /** Parse the body as JSON. Throws BadRequest (HTTP 400) on bad input unless a default is given. */
  json(fallback = MISSING) {
    try {
      return decodeJson(this.body, "Request body");
    } catch (err) {
      if (fallback !== MISSING && err instanceof BadRequest) return fallback;
      throw err;
    }
  }

  form() {
    return Object.fromEntries(new URLSearchParams(this.text()));
  }

  static decodeBody(body, isBase64 = false) {
    if (body === null || body === undefined) return Buffer.alloc(0);
    if (Buffer.isBuffer(body)) return isBase64 ? Buffer.from(body.toString("ascii"), "base64") : body;
    if (typeof body === "object") return Buffer.from(JSON.stringify(body), "utf8");
    if (isBase64) return Buffer.from(String(body), "base64");
    return Buffer.from(String(body), "utf8");
  }
}

/** One message / object notification inside a batch event. */
class Record {
  constructor(init = {}) {
    this.id = init.id === undefined ? null : init.id;
    this.body = init.body === undefined ? null : init.body;
    this.attributes = Object.assign({}, init.attributes || {});
    this.source = init.source === undefined ? null : init.source;
    this.bucket = init.bucket === undefined ? null : init.bucket;
    this.key = init.key === undefined ? null : init.key;
    this.size = init.size === undefined ? null : init.size;
    this.action = init.action === undefined ? null : init.action; // "created" | "deleted"
    this.raw = init.raw === undefined ? null : init.raw;
  }

  text() {
    if (Buffer.isBuffer(this.body)) return this.body.toString("utf8");
    if (this.body !== null && typeof this.body === "object") return JSON.stringify(this.body);
    return this.body === null || this.body === undefined ? "" : String(this.body);
  }

  json(fallback = MISSING) {
    if (this.body !== null && typeof this.body === "object" && !Buffer.isBuffer(this.body)) return this.body;
    try {
      return decodeJson(this.text(), `Record ${this.id || ""}`.trim() + " body");
    } catch (err) {
      if (fallback !== MISSING && err instanceof BadRequest) return fallback;
      throw err;
    }
  }
}

class Event {
  /**
   * @param {{type: string, provider?: string, function?: string, http?: HttpRequest|null, records?: Record[],
   *          data?: any, time?: Date, source?: string|null, raw?: any}} init
   */
  constructor(init = {}) {
    this.type = init.type;
    this.provider = init.provider || "local";
    this.function = init.function || "";
    this.http = init.http || null;
    this.records = Array.from(init.records || []);
    this.data = init.data === undefined ? null : init.data;
    this.time = init.time instanceof Date ? init.time : init.time ? parseTime(init.time) : new Date();
    this.source = init.source === undefined ? null : init.source;
    this.raw = init.raw === undefined ? null : init.raw;
  }

  get isHttp() {
    return this.type === EventType.HTTP;
  }

  get isBatch() {
    return this.type === EventType.QUEUE || this.type === EventType.TOPIC || this.type === EventType.STORAGE;
  }

  /** HTTP: the parsed body; batches: the first record's body; otherwise `data`. */
  json(fallback = MISSING) {
    if (this.http) return fallback === MISSING ? this.http.json() : this.http.json(fallback);
    if (this.records.length) return fallback === MISSING ? this.records[0].json() : this.records[0].json(fallback);
    return this.data;
  }

  [Symbol.iterator]() {
    return this.records[Symbol.iterator]();
  }

  /** JSON-friendly summary (same as Python `Event.to_dict()`). */
  toDict() {
    const out = {
      type: this.type,
      provider: this.provider,
      function: this.function,
      time: isoformat(this.time),
      source: this.source,
    };
    if (this.http) {
      out.http = { method: this.http.method, path: this.http.path, query: this.http.query, path_params: this.http.pathParams };
    }
    if (this.records.length) out.records = this.records.length;
    if (this.data !== null && this.data !== undefined) out.data = this.data;
    return out;
  }

  /** The full portable form used by the worker protocol (Python `Event.to_wire()`). */
  toWire() {
    const out = {
      type: this.type,
      provider: this.provider,
      function: this.function,
      time: isoformat(this.time),
      source: this.source,
      data: this.data,
      http: null,
      records: [],
    };
    if (this.http) {
      out.http = {
        method: this.http.method,
        path: this.http.path,
        headers: this.http.headers.toObject(),
        query: this.http.query,
        multi_query: this.http.multiQuery,
        path_params: this.http.pathParams,
        body_b64: this.http.body.toString("base64"),
        source_ip: this.http.sourceIp,
        route: this.http.route,
      };
    }
    out.records = this.records.map((r) => {
      const binary = Buffer.isBuffer(r.body);
      return {
        id: r.id,
        body: binary ? null : r.body,
        body_b64: binary ? r.body.toString("base64") : null,
        attributes: r.attributes,
        source: r.source,
        bucket: r.bucket,
        key: r.key,
        size: r.size,
        action: r.action,
      };
    });
    return out;
  }
}

/** Parse the many timestamp shapes providers emit; fall back to now. */
function parseTime(value) {
  if (value instanceof Date) return value;
  if (typeof value === "number") return new Date(value > 1e11 ? value : value * 1000);
  if (typeof value === "string" && value.trim()) {
    const text = value.trim();
    if (/^\d+$/.test(text)) return parseTime(Number(text));
    const d = new Date(/([zZ]|[+-]\d\d:?\d\d)$/.test(text) || !/T|\d:\d/.test(text) ? text : `${text}Z`);
    if (!Number.isNaN(d.getTime())) return d;
  }
  return new Date();
}

/** Build an Event from the worker protocol's portable form (inverse of toWire). */
function eventFromWire(d) {
  const src = d || {};
  let http = null;
  if (src.http) {
    const h = src.http;
    http = new HttpRequest({
      method: h.method,
      path: h.path,
      headers: h.headers || {},
      query: h.query || {},
      multiQuery: h.multi_query || {},
      pathParams: h.path_params || {},
      body: h.body_b64 ? Buffer.from(h.body_b64, "base64") : h.body !== undefined && h.body !== null ? h.body : null,
      sourceIp: h.source_ip || null,
      route: h.route || null,
    });
  }
  const records = (src.records || []).map(
    (r) =>
      new Record({
        id: r.id,
        body: r.body_b64 ? Buffer.from(r.body_b64, "base64") : r.body,
        attributes: r.attributes || {},
        source: r.source,
        bucket: r.bucket,
        key: r.key,
        size: r.size,
        action: r.action,
      }),
  );
  return new Event({
    type: src.type,
    provider: src.provider || "local",
    function: src.function || "",
    http,
    records,
    data: src.data === undefined ? null : src.data,
    time: src.time ? parseTime(src.time) : new Date(),
    source: src.source === undefined ? null : src.source,
  });
}

module.exports = {
  EventType,
  Headers,
  HttpRequest,
  Record,
  Event,
  parseTime,
  parseCookies,
  eventFromWire,
  /** Alias named in deploy_docs/NODE_RUNTIME.md. */
  eventFromDict: eventFromWire,
};
