"use strict";
/**
 * Google Cloud Functions (2nd gen) adapter (port of runtime/adapters/gcp.py).
 *
 * The generated `pskit_entry.js` registers two functions-framework entry points:
 *
 * - `pskit_http` -> `http(req, res)` (Express request/response). A body carrying
 *   the `__pskit` envelope (Cloud Scheduler, Cloud Workflows, `invoke()`) is run as
 *   a non-HTTP event and answered with the raw JSON result, or a 500
 *   `{"errorType", "cause"}` that the workflow compiler understands.
 * - `pskit_event` -> `cloudEvent(ce)`: Pub/Sub `messagePublished` (queue / topic)
 *   and Cloud Storage object events.
 */

const crypto = require("crypto");
const { Context } = require("../context");
const { errorName, errorText } = require("../errors");
const { execute } = require("../dispatch");
const { Event, EventType, Headers, HttpRequest, Record, parseTime } = require("../event");
const { dumps, toResponse } = require("../response");
const { actionFrom, b64Text, functionName, unwrapEnvelope } = require("./base");

const PROVIDER = "gcp";
const JSON_TYPE = "application/json";

function makeContext(fn, requestId, raw) {
  return new Context({ requestId: requestId || crypto.randomUUID(), function: fn, provider: PROVIDER, raw });
}

function headerOf(headers, name) {
  if (!headers) return undefined;
  if (typeof headers.get === "function") return headers.get(name);
  const lower = name.toLowerCase();
  for (const [k, v] of Object.entries(headers)) if (k.toLowerCase() === lower) return Array.isArray(v) ? v[0] : v;
  return undefined;
}

function requestId(headers) {
  for (const key of ["Function-Execution-Id", "X-Cloud-Trace-Context"]) {
    const value = headerOf(headers, key);
    if (value) return String(value).split("/")[0];
  }
  return null;
}

function rawBody(req) {
  if (Buffer.isBuffer(req.rawBody)) return req.rawBody;
  const body = req.body;
  if (body === undefined || body === null) return Buffer.alloc(0);
  if (Buffer.isBuffer(body)) return body;
  if (typeof body === "string") return Buffer.from(body, "utf8");
  if (typeof body === "object" && Object.keys(body).length === 0) return Buffer.alloc(0);
  return Buffer.from(JSON.stringify(body), "utf8");
}

// ------------------------------------------------------------------ HTTP

function toHttpEvent(req, fn) {
  const headers = Object.assign({}, req.headers || {});
  const multi = {};
  for (const [k, v] of Object.entries(req.query || {})) multi[k] = Array.isArray(v) ? v.map(String) : [String(v)];
  const query = {};
  for (const [k, v] of Object.entries(multi)) query[k] = v.length ? v[v.length - 1] : "";
  const forwarded = String(headerOf(headers, "x-forwarded-for") || "").split(",")[0].trim();
  const http = new HttpRequest({
    method: req.method,
    path: req.path || "/",
    headers: new Headers(headers),
    query,
    multiQuery: multi,
    body: rawBody(req),
    sourceIp: forwarded || req.ip || null,
  });
  return new Event({ type: EventType.HTTP, provider: PROVIDER, function: fn, http, raw: req });
}

function send(res, status, headers, body, cookies) {
  res.status(status);
  for (const [k, v] of Object.entries(headers)) res.set(k, v);
  for (const c of cookies || []) res.append("set-cookie", c);
  res.send(body);
}

async function http(req, res) {
  const fn = functionName();
  const body = rawBody(req);
  const reqId = requestId(req.headers);
  const wrapped = body[0] === 0x7b ? unwrapEnvelope(body) : null;
  if (wrapped) {
    const event = new Event({ type: wrapped[0], provider: PROVIDER, function: fn, data: wrapped[1], source: (wrapped[2].source || null), raw: req });
    let result;
    try {
      result = await execute(event, makeContext(fn, reqId, req));
    } catch (err) {
      const payload = { errorType: errorName(err), cause: errorText(err) };
      return send(res, 500, { "content-type": JSON_TYPE }, Buffer.from(dumps(payload), "utf8"));
    }
    return send(res, 200, { "content-type": JSON_TYPE }, Buffer.from(dumps(result === undefined ? null : result), "utf8"));
  }
  const event = toHttpEvent(req, fn);
  const resp = toResponse(await execute(event, makeContext(fn, reqId, req)));
  const { status, headers, body: out } = resp.render();
  return send(res, status, headers, out, resp.cookies);
}

// ------------------------------------------------------------------ CloudEvents

function ceData(ce) {
  let data = ce ? ce.data : null;
  if (Buffer.isBuffer(data)) data = data.toString("utf8");
  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch (err) {
      /* keep the text */
    }
  }
  return data;
}

function storageWanted(key) {
  const prefix = process.env.PSKIT_STORAGE_PREFIX || "";
  const suffix = process.env.PSKIT_STORAGE_SUFFIX || "";
  return key.startsWith(prefix) && key.endsWith(suffix);
}

/** Translate a CloudEvent; returns null when filtered out (storage prefix/suffix). */
function toCloudEvent(ce, fn = "") {
  const ceType = String((ce && ce.type) || "");
  const source = (ce && ce.source) || null;
  const when = parseTime(ce && ce.time);
  const data = ceData(ce) || {};
  if (ceType.startsWith("google.cloud.pubsub.topic")) {
    const msg = data.message || {};
    const body = b64Text(msg.data);
    const wrapped = typeof body === "string" ? unwrapEnvelope(body) : null;
    if (wrapped) {
      return new Event({
        type: wrapped[0],
        provider: PROVIDER,
        function: fn,
        data: wrapped[1],
        time: when,
        source: (wrapped[2].source || null) || source,
        raw: ce,
      });
    }
    const kind = process.env.PSKIT_TRIGGER_KIND === "queue" ? EventType.QUEUE : EventType.TOPIC;
    const record = new Record({
      id: msg.messageId || msg.message_id || (ce && ce.id) || null,
      body,
      attributes: Object.assign({}, msg.attributes || {}),
      source: data.subscription || source,
      raw: msg,
    });
    return new Event({ type: kind, provider: PROVIDER, function: fn, records: [record], time: when, source, raw: ce });
  }
  if (ceType.startsWith("google.cloud.storage.object")) {
    const key = data.name || "";
    if (!storageWanted(key)) return null;
    const size = data.size;
    const record = new Record({
      id: String(data.generation || (ce && ce.id) || ""),
      bucket: data.bucket || null,
      key,
      size: size !== undefined && size !== null && size !== "" ? Number(size) : null,
      action: actionFrom(ceType.split(".").pop()),
      attributes: { content_type: data.contentType, event_type: ceType },
      source,
      raw: data,
    });
    return new Event({ type: EventType.STORAGE, provider: PROVIDER, function: fn, records: [record], time: when, source, raw: ce });
  }
  return new Event({ type: EventType.INVOKE, provider: PROVIDER, function: fn, data, time: when, source, raw: ce });
}

async function cloudEvent(ce) {
  const fn = functionName();
  const event = toCloudEvent(ce, fn);
  if (!event) return null;
  return execute(event, makeContext(fn, (ce && ce.id) || null, ce));
}

module.exports = { PROVIDER, toHttpEvent, http, toCloudEvent, cloudEvent };
