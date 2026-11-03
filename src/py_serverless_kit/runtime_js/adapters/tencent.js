"use strict";
/**
 * Tencent Cloud SCF adapter (port of runtime/adapters/tencent.py).
 *
 * Handles API Gateway (integrated response), timer triggers, COS triggers and
 * direct invocation. The generated `index.js` exports `main_handler`.
 */

const { Context } = require("../context");
const { execute } = require("../dispatch");
const { Event, EventType, Headers, HttpRequest, Record, parseTime } = require("../event");
const { actionFrom, functionName, maybeJson, unwrapEnvelope } = require("./base");

const PROVIDER = "tencent";

function isObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v) && !Buffer.isBuffer(v);
}

function ctxGet(ctx, key, fallback = null) {
  if (!ctx) return fallback;
  const value = ctx[key];
  return value === undefined || value === null ? fallback : value;
}

function parseQuery(text) {
  const multi = {};
  for (const [k, v] of new URLSearchParams(text)) (multi[k] = multi[k] || []).push(v);
  return multi;
}

function toHttp(evt) {
  const rc = evt.requestContext || {};
  let query = {};
  let multi = {};
  const rawQuery = evt.queryString;
  if (isObject(rawQuery)) {
    for (const [key, value] of Object.entries(rawQuery)) {
      const values = Array.isArray(value) ? value.map(String) : [String(value)];
      multi[key] = values;
      query[key] = values.length ? values[values.length - 1] : "";
    }
  } else if (typeof rawQuery === "string" && rawQuery) {
    multi = parseQuery(rawQuery);
    for (const [k, v] of Object.entries(multi)) query[k] = v[v.length - 1];
  }
  if (!Object.keys(query).length && evt.queryStringParameters) {
    query = {};
    for (const [k, v] of Object.entries(evt.queryStringParameters)) query[k] = String(v);
  }
  const pathParams = {};
  for (const [k, v] of Object.entries(evt.pathParameters || {})) pathParams[k] = String(v);
  return new HttpRequest({
    method: evt.httpMethod || rc.httpMethod || "GET",
    path: evt.path || rc.path || "/",
    headers: new Headers(evt.headers || {}),
    query,
    multiQuery: multi,
    pathParams,
    body: HttpRequest.decodeBody(evt.body, Boolean(evt.isBase64Encoded)),
    sourceIp: rc.sourceIp || null,
  });
}

function decodePlus(text) {
  try {
    return decodeURIComponent(String(text).replace(/\+/g, " "));
  } catch (err) {
    return String(text);
  }
}

function cosEvent(evt, fn) {
  const records = (evt.Records || []).map((r) => {
    const cos = r.cos || {};
    const obj = cos.cosObject || {};
    const bucket = (cos.cosBucket || {}).name || null;
    let key = obj.key || "";
    // COS keys look like "/<appid>/<bucket>/<path>"; strip that prefix.
    const trimmed = key.replace(/^\/+/, "");
    const parts = trimmed.split("/");
    if (parts.length >= 3 && /^\d+$/.test(parts[0])) key = parts.slice(2).join("/");
    const eventName = (r.event || {}).eventName || "";
    return new Record({
      id: (obj.meta || {})["x-cos-request-id"] || null,
      bucket,
      key: decodePlus(key),
      size: obj.size === undefined ? null : obj.size,
      action: actionFrom(eventName),
      attributes: { event_name: eventName, url: obj.url },
      source: "cos",
      raw: r,
    });
  });
  const first = (evt.Records || [{}])[0] || {};
  return new Event({
    type: EventType.STORAGE,
    provider: PROVIDER,
    function: fn,
    records,
    source: "cos",
    time: parseTime((first.event || {}).eventTime),
    raw: evt,
  });
}

function toEvent(native, ctx) {
  const fn = functionName(ctxGet(ctx, "function_name", "") || "");
  const evt = maybeJson(native);
  const wrapped = unwrapEnvelope(evt);
  if (wrapped !== null) {
    const [kind, data, meta] = wrapped;
    return new Event({ type: kind, provider: PROVIDER, function: fn, data, source: meta.source || null, raw: evt });
  }
  if (isObject(evt)) {
    if ("httpMethod" in evt && ("requestContext" in evt || "path" in evt)) {
      return new Event({ type: EventType.HTTP, provider: PROVIDER, function: fn, http: toHttp(evt), raw: evt });
    }
    if (evt.Type === "Timer") {
      const message = evt.Message;
      const inner = message ? unwrapEnvelope(message) : null;
      return new Event({
        type: EventType.SCHEDULE,
        provider: PROVIDER,
        function: fn,
        data: inner ? inner[1] : message ? maybeJson(message) : null,
        time: parseTime(evt.Time),
        source: evt.TriggerName || null,
        raw: evt,
      });
    }
    const records = evt.Records;
    if (Array.isArray(records) && records.length && isObject(records[0]) && "cos" in records[0]) {
      return cosEvent(evt, fn);
    }
  }
  return new Event({ type: EventType.INVOKE, provider: PROVIDER, function: fn, data: evt, raw: native });
}

function toContext(ctx, fn) {
  if (!ctx) return new Context({ function: fn, provider: PROVIDER });
  const limitMs = ctxGet(ctx, "time_limit_in_ms");
  const memory = ctxGet(ctx, "memory_limit_in_mb");
  return new Context({
    requestId: String(ctxGet(ctx, "request_id", "") || ""),
    function: fn,
    provider: PROVIDER,
    memoryMb: memory ? Number(memory) : null,
    deadline: limitMs ? Date.now() / 1000 + Number(limitMs) / 1000 : null,
    raw: ctx,
  });
}

function toNative(result, event) {
  if (event.http) {
    const { status, headers, body, isBase64 } = result.renderForGateway();
    const cookies = result.cookies || [];
    if (cookies.length) headers["set-cookie"] = cookies.length === 1 ? cookies[0] : cookies.join(", ");
    return { isBase64Encoded: isBase64, statusCode: status, headers, body };
  }
  return result;
}

/** SCF entrypoint - the generated `index.main_handler` points here. */
async function main_handler(native, ctx) {
  const event = toEvent(native, ctx);
  const context = toContext(ctx, event.function);
  return toNative(await execute(event, context), event);
}

module.exports = { PROVIDER, toEvent, toContext, toNative, main_handler, handler: main_handler };
