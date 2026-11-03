"use strict";
/**
 * Huawei Cloud FunctionGraph adapter (port of runtime/adapters/huawei.py).
 *
 * Handles APIG (dedicated gateway) events, timer triggers, OBS triggers, SMN
 * topic triggers and direct invocation. The generated `index.js` exports `handler`.
 */

const { Context } = require("../context");
const { execute } = require("../dispatch");
const { Event, EventType, Headers, HttpRequest, Record, parseTime } = require("../event");
const { actionFrom, functionName, maybeJson, unwrapEnvelope } = require("./base");

const PROVIDER = "huawei";

function isObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v) && !Buffer.isBuffer(v);
}

/** Call a context accessor such as `getRequestID()`; best effort. */
function call(ctx, method, fallback = null) {
  if (ctx && typeof ctx[method] === "function") {
    try {
      return ctx[method]();
    } catch (err) {
      return fallback;
    }
  }
  return fallback;
}

function toHttp(evt) {
  const rc = evt.requestContext || {};
  const query = {};
  const multi = {};
  for (const [key, value] of Object.entries(evt.queryStringParameters || {})) {
    const values = Array.isArray(value) ? value.map(String) : [String(value)];
    multi[key] = values;
    query[key] = values.length ? values[values.length - 1] : "";
  }
  const pathParams = {};
  for (const [k, v] of Object.entries(evt.pathParameters || {})) pathParams[k] = String(v);
  return new HttpRequest({
    method: evt.httpMethod || "GET",
    path: evt.path || "/",
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

function obsEvent(evt, fn) {
  const records = (evt.Records || []).map((r) => {
    const obs = r.obs || r.s3 || {};
    const obj = obs.object || {};
    return new Record({
      id: obj.sequencer || null,
      bucket: (obs.bucket || {}).name || null,
      key: decodePlus(obj.key || ""),
      size: obj.size === undefined ? null : obj.size,
      action: actionFrom(r.eventName || ""),
      attributes: { event_name: r.eventName, etag: obj.eTag },
      source: "obs",
      raw: r,
    });
  });
  const first = (evt.Records || [{}])[0] || {};
  return new Event({
    type: EventType.STORAGE,
    provider: PROVIDER,
    function: fn,
    records,
    source: "obs",
    time: parseTime(first.eventTime),
    raw: evt,
  });
}

function smnEvent(evt, fn) {
  const records = (evt.record || []).map((r) => {
    const smn = r.smn || {};
    return new Record({
      id: smn.message_id || null,
      body: smn.message === undefined ? null : smn.message,
      attributes: Object.assign({ subject: smn.subject }, smn.message_attributes || {}),
      source: smn.topic_urn || null,
      raw: r,
    });
  });
  const first = ((evt.record || [{}])[0] || {}).smn || {};
  return new Event({
    type: EventType.TOPIC,
    provider: PROVIDER,
    function: fn,
    records,
    source: first.topic_urn || null,
    time: parseTime(first.timestamp),
    raw: evt,
  });
}

function toEvent(native, ctx) {
  const fn = functionName(call(ctx, "getFunctionName", "") || "");
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
    if (String(evt.trigger_type || "").toUpperCase() === "TIMER") {
      const userEvent = evt.user_event;
      const inner = userEvent ? unwrapEnvelope(userEvent) : null;
      return new Event({
        type: EventType.SCHEDULE,
        provider: PROVIDER,
        function: fn,
        data: inner ? inner[1] : userEvent ? maybeJson(userEvent) : null,
        time: parseTime(evt.time),
        source: evt.trigger_name || null,
        raw: evt,
      });
    }
    const records = evt.Records;
    if (Array.isArray(records) && records.length && isObject(records[0]) && ("obs" in records[0] || "s3" in records[0])) {
      return obsEvent(evt, fn);
    }
    const smn = evt.record;
    if (Array.isArray(smn) && smn.length && isObject(smn[0]) && "smn" in smn[0]) return smnEvent(evt, fn);
  }
  return new Event({ type: EventType.INVOKE, provider: PROVIDER, function: fn, data: evt, raw: native });
}

function toContext(ctx, fn) {
  if (!ctx) return new Context({ function: fn, provider: PROVIDER });
  const memory = call(ctx, "getMemorySize");
  const remainingMs = call(ctx, "getRemainingTimeInMilliSeconds");
  const remaining = typeof ctx.getRemainingTimeInMilliSeconds === "function" ? () => ctx.getRemainingTimeInMilliSeconds() : undefined;
  return new Context({
    requestId: String(call(ctx, "getRequestID", "") || ""),
    function: fn,
    provider: PROVIDER,
    memoryMb: memory ? Number(memory) : null,
    deadline: remainingMs ? Date.now() / 1000 + Number(remainingMs) / 1000 : null,
    raw: ctx,
    remaining,
  });
}

function toNative(result, event) {
  if (event.http) {
    const { status, headers, body, isBase64 } = result.renderForGateway();
    const cookies = result.cookies || [];
    if (cookies.length) headers["set-cookie"] = cookies.length === 1 ? cookies[0] : cookies.join(", ");
    return { statusCode: status, isBase64Encoded: isBase64, headers, body };
  }
  return result;
}

/** FunctionGraph entrypoint - the generated `index.handler` points here. */
async function handler(native, ctx) {
  const event = toEvent(native, ctx);
  const context = toContext(ctx, event.function);
  return toNative(await execute(event, context), event);
}

module.exports = { PROVIDER, toEvent, toContext, toNative, handler };
