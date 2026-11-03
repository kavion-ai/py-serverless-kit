"use strict";
/**
 * Azure Functions (Node.js v4 programming model) adapter (port of runtime/adapters/azure.py).
 *
 * The generated `pskit_entry.js` registers one `app.http()` / `app.timer()` /
 * `app.storageQueue()` / `app.storageBlob()` / `app.serviceBusTopic()` per trigger and
 * calls these helpers with the *logical* function name, because one Function App
 * hosts every function of the service (app settings are shared, so
 * `PSKIT_FUNCTION` cannot be used).
 *
 * `@azure/functions` is not imported here: handlers return plain `HttpResponseInit`
 * objects, so the module is testable without the Azure SDK.
 */

const crypto = require("crypto");
const { Context } = require("../context");
const { errorName, errorText } = require("../errors");
const { execute } = require("../dispatch");
const { Event, EventType, Headers, HttpRequest, Record, parseTime } = require("../event");
const { dumps, toResponse } = require("../response");
const { unwrapEnvelope } = require("./base");

const PROVIDER = "azure";
const JSON_TYPE = "application/json";

function makeContext(fn, requestId, raw) {
  return new Context({ requestId: requestId || crypto.randomUUID(), function: fn, provider: PROVIDER, raw });
}

function meta(ctx) {
  return (ctx && ctx.triggerMetadata) || {};
}

function headerEntries(headers) {
  if (!headers) return [];
  if (typeof headers.entries === "function") return Array.from(headers.entries());
  return Object.entries(headers);
}

function textOf(value) {
  if (Buffer.isBuffer(value)) return value.toString("utf8");
  return value === undefined ? null : value;
}

// ------------------------------------------------------------------ HTTP

async function readBody(req) {
  if (typeof req.arrayBuffer === "function") return Buffer.from(await req.arrayBuffer());
  if (Buffer.isBuffer(req.body)) return req.body;
  if (typeof req.body === "string") return Buffer.from(req.body, "utf8");
  return Buffer.alloc(0);
}

function toHttpEvent(req, fn, body) {
  const headers = headerEntries(req.headers);
  const url = new URL(req.url || "http://localhost/");
  const multi = {};
  for (const [k, v] of url.searchParams.entries()) (multi[k] = multi[k] || []).push(v);
  const query = {};
  for (const [k, v] of Object.entries(multi)) query[k] = v[v.length - 1];
  const lookup = {};
  for (const [k, v] of headers) lookup[String(k).toLowerCase()] = String(v);
  const forwarded = (lookup["x-forwarded-for"] || "").split(",")[0].split(":")[0];
  const http = new HttpRequest({
    method: req.method,
    path: url.pathname || "/",
    headers: new Headers(headers),
    query,
    multiQuery: multi,
    pathParams: Object.assign({}, req.params || {}),
    body,
    sourceIp: forwarded || null,
  });
  return new Event({ type: EventType.HTTP, provider: PROVIDER, function: fn, http, raw: req });
}

async function http(req, ctx, fn) {
  const body = await readBody(req);
  const lookup = {};
  for (const [k, v] of headerEntries(req.headers)) lookup[String(k).toLowerCase()] = String(v);
  const reqId = lookup["x-ms-request-id"] || lookup["x-request-id"] || (ctx && ctx.invocationId) || null;
  const wrapped = body[0] === 0x7b ? unwrapEnvelope(body) : null;
  if (wrapped) {
    const event = new Event({ type: wrapped[0], provider: PROVIDER, function: fn, data: wrapped[1], source: (wrapped[2].source || null), raw: req });
    try {
      const result = await execute(event, makeContext(fn, reqId, req), fn);
      return { status: 200, headers: { "content-type": JSON_TYPE }, body: dumps(result === undefined ? null : result) };
    } catch (err) {
      const payload = { errorType: errorName(err), cause: errorText(err) };
      return { status: 500, headers: { "content-type": JSON_TYPE }, body: dumps(payload) };
    }
  }
  const event = toHttpEvent(req, fn, body);
  const resp = toResponse(await execute(event, makeContext(fn, reqId, req), fn));
  const { status, headers, body: out } = resp.render();
  // A list of pairs keeps every Set-Cookie header.
  const pairs = Object.entries(headers).concat((resp.cookies || []).map((c) => ["set-cookie", c]));
  return { status, headers: pairs, body: out };
}

// ------------------------------------------------------------------ other triggers

async function timer(timerInfo, ctx, fn, data = null) {
  const event = new Event({ type: EventType.SCHEDULE, provider: PROVIDER, function: fn, data, source: "azure.timer", raw: timerInfo });
  return execute(event, makeContext(fn, ctx && ctx.invocationId, timerInfo), fn);
}

function toQueueEvent(message, ctx, fn) {
  const m = meta(ctx);
  const record = new Record({
    id: m.id || null,
    body: textOf(message),
    attributes: { dequeue_count: m.dequeueCount === undefined ? null : m.dequeueCount, insertion_time: String(m.insertionTime || "") },
    source: "azure.storage.queue",
    raw: message,
  });
  return new Event({
    type: EventType.QUEUE,
    provider: PROVIDER,
    function: fn,
    records: [record],
    time: parseTime(m.insertionTime),
    source: "azure.storage.queue",
    raw: message,
  });
}

async function queue(message, ctx, fn) {
  return execute(toQueueEvent(message, ctx, fn), makeContext(fn, meta(ctx).id || (ctx && ctx.invocationId), message), fn);
}

function toBlobEvent(blob, ctx, fn, bucket) {
  const m = meta(ctx);
  const name = String(m.blobTrigger || m.name || "");
  const key = name.startsWith(`${bucket}/`) ? name.slice(bucket.length + 1) : name;
  const record = new Record({
    id: m.uri || name,
    bucket,
    key,
    size: Buffer.isBuffer(blob) ? blob.length : (m.properties && m.properties.length) || null,
    action: "created",
    attributes: { uri: m.uri || null },
    source: "azure.storage.blob",
    raw: blob,
  });
  return new Event({ type: EventType.STORAGE, provider: PROVIDER, function: fn, records: [record], source: "azure.storage.blob", raw: blob });
}

async function blob(blobData, ctx, fn, bucket) {
  return execute(toBlobEvent(blobData, ctx, fn, bucket), makeContext(fn, ctx && ctx.invocationId, blobData), fn);
}

function toServiceBusEvent(message, ctx, fn) {
  const m = meta(ctx);
  const props = m.applicationProperties || m.userProperties || {};
  const attributes = {};
  for (const [k, v] of Object.entries(props)) attributes[String(k)] = v;
  const record = new Record({ id: m.messageId || null, body: textOf(message), attributes, source: "azure.servicebus", raw: message });
  return new Event({
    type: EventType.TOPIC,
    provider: PROVIDER,
    function: fn,
    records: [record],
    time: parseTime(m.enqueuedTimeUtc),
    source: "azure.servicebus",
    raw: message,
  });
}

async function serviceBus(message, ctx, fn) {
  return execute(toServiceBusEvent(message, ctx, fn), makeContext(fn, meta(ctx).messageId || (ctx && ctx.invocationId), message), fn);
}

module.exports = {
  PROVIDER,
  toHttpEvent,
  http,
  timer,
  toQueueEvent,
  queue,
  toBlobEvent,
  blob,
  toServiceBusEvent,
  serviceBus,
};
