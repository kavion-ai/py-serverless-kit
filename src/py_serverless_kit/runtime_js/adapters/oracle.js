"use strict";
/**
 * Oracle Cloud (OCI) Functions adapter on the Fn Project Node.js FDK
 * (port of runtime/adapters/oracle.py).
 *
 * The generated `func.js` runs `fdk.handle(handler, {inputMode: "buffer"})`.
 * Invocations come from:
 *
 * - OCI API Gateway: `ctx.httpGateway` (method, request URL, headers), or the
 *   `Fn-Http-Method` / `Fn-Http-Request-Url` / `Fn-Http-H-<name>` protocol headers;
 * - OCI Events (object storage): a CloudEvents JSON body;
 * - direct invoke (`oci fn function invoke`) / the `__pskit` envelope.
 */

const { Context } = require("../context");
const { Event, EventType, Headers, HttpRequest, Record, parseTime } = require("../event");
const { actionFrom, functionName, maybeJson, unwrapEnvelope } = require("./base");
const { eventFromRequest, run } = require("./httpfn");

const PROVIDER = "oracle";
const HEADER_PREFIX = "fn-http-h-";

function firstOf(value) {
  if (Array.isArray(value)) return value.length ? value[0] : null;
  return value === undefined ? null : value;
}

function lowerHeaders(raw) {
  const out = {};
  for (const [k, v] of Object.entries(raw || {})) out[String(k).toLowerCase()] = v;
  return out;
}

function toBuffer(data) {
  if (data === null || data === undefined) return Buffer.alloc(0);
  if (Buffer.isBuffer(data)) return data;
  if (data instanceof Uint8Array) return Buffer.from(data);
  if (typeof data === "string") return Buffer.from(data, "utf8");
  return Buffer.from(JSON.stringify(data), "utf8");
}

function toRequest(ctx, body) {
  const headers = lowerHeaders((ctx && ctx.headers) || {});
  const gw = ctx && ctx.httpGateway;
  let method = firstOf(headers["fn-http-method"]);
  if (!method && gw) method = gw.method;
  if (!method) return null;
  const url = firstOf(headers["fn-http-request-url"]) || (gw && gw.requestURL) || "/";
  let httpHeaders = {};
  if (gw && gw.headers && Object.keys(gw.headers).length) {
    for (const [k, v] of Object.entries(gw.headers)) httpHeaders[k] = firstOf(v);
  } else {
    for (const [k, v] of Object.entries(headers)) if (k.startsWith(HEADER_PREFIX)) httpHeaders[k.slice(HEADER_PREFIX.length)] = firstOf(v);
  }
  const parsed = new URL(String(url), "http://oci.invalid");
  const multi = {};
  for (const [k, v] of parsed.searchParams) (multi[k] = multi[k] || []).push(v);
  const query = {};
  for (const [k, v] of Object.entries(multi)) query[k] = v[v.length - 1];
  return new HttpRequest({
    method: String(method),
    path: parsed.pathname || "/",
    headers: new Headers(httpHeaders),
    query,
    multiQuery: multi,
    body,
  });
}

function cloudEvent(payload, fn) {
  const etype = String(payload.eventType || payload.type || "");
  if (!etype.includes("objectstorage")) return null;
  const data = payload.data || {};
  const details = data.additionalDetails || {};
  const record = new Record({
    id: String(payload.eventID || payload.id || ""),
    bucket: details.bucketName || null,
    key: data.resourceName || null,
    action: actionFrom(etype),
    attributes: { event_type: etype, namespace: details.namespace },
    source: String(payload.source || "objectstorage"),
    raw: payload,
  });
  return new Event({
    type: EventType.STORAGE,
    provider: PROVIDER,
    function: fn,
    records: [record],
    source: record.source,
    time: parseTime(payload.eventTime || payload.time),
    raw: payload,
  });
}

function toEvent(ctx, data, fn) {
  const body = toBuffer(data);
  const req = toRequest(ctx, body);
  if (req !== null) return eventFromRequest(req, PROVIDER, fn, ctx);
  const payload = body.length ? maybeJson(body) : null;
  const wrapped = unwrapEnvelope(payload);
  if (wrapped !== null) {
    const [kind, value, meta] = wrapped;
    return new Event({ type: kind, provider: PROVIDER, function: fn, data: value, source: meta.source || null, raw: payload });
  }
  if (payload && typeof payload === "object" && !Array.isArray(payload) && !Buffer.isBuffer(payload)) {
    const storage = cloudEvent(payload, fn);
    if (storage !== null) return storage;
  }
  return new Event({ type: EventType.INVOKE, provider: PROVIDER, function: fn, data: payload, raw: payload });
}

/** Set status and headers on the FDK context (HTTP gateway when present). */
function respond(ctx, status, headers, isHttp) {
  if (!ctx) return;
  const gw = isHttp ? ctx.httpGateway : null;
  if (gw) {
    if (typeof gw.setStatusCode === "function") gw.setStatusCode(status);
    else gw.statusCode = status;
  }
  const target = gw && typeof gw.setResponseHeader === "function" ? gw : ctx;
  for (const [k, v] of Object.entries(headers)) {
    if (k.toLowerCase() === "content-type") {
      ctx.responseContentType = v;
      continue;
    }
    if (typeof target.setResponseHeader === "function") target.setResponseHeader(k, v);
  }
  if (isHttp && !gw && typeof ctx.setResponseHeader === "function") ctx.setResponseHeader("Fn-Http-Status", String(status));
}

/** FDK entrypoint used by the generated `func.js`: `handler(input, ctx)`. */
async function handler(input, ctx) {
  const fn = functionName();
  const event = toEvent(ctx, input, fn);
  const context = new Context({ requestId: String((ctx && (ctx.callID || ctx.callId)) || "") || undefined, function: fn, provider: PROVIDER, raw: ctx });
  const { status, headers, body, isBase64 } = await run(event, context);
  respond(ctx, status, headers, event.http !== null);
  return isBase64 ? Buffer.from(body, "base64") : body;
}

module.exports = { PROVIDER, toRequest, toEvent, handler };
