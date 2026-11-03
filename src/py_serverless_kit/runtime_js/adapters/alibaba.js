"use strict";
/**
 * Alibaba Cloud Function Compute 3.0 adapter (port of runtime/adapters/alibaba.py).
 *
 * Handles HTTP triggers (event handler mode), timer triggers, OSS triggers, MNS
 * topic triggers and direct invocation. FC passes the event as a Buffer.
 * The generated `index.js` exports `handler` from here (`index.handler`).
 */

const { Context } = require("../context");
const { execute } = require("../dispatch");
const { Event, EventType, Headers, HttpRequest, Record, parseTime } = require("../event");
const { actionFrom, functionName, maybeJson, unwrapEnvelope } = require("./base");

const PROVIDER = "alibaba";

function isObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v) && !Buffer.isBuffer(v);
}

function toHttp(evt) {
  const rc = evt.requestContext || {};
  const http = rc.http || {};
  const query = {};
  const multi = {};
  for (const [key, value] of Object.entries(evt.queryParameters || {})) {
    const values = Array.isArray(value) ? value.map(String) : [String(value)];
    multi[key] = values;
    query[key] = values.length ? values[values.length - 1] : "";
  }
  return new HttpRequest({
    method: http.method || "GET",
    path: evt.rawPath || http.path || "/",
    headers: new Headers(evt.headers || {}),
    query,
    multiQuery: multi,
    body: HttpRequest.decodeBody(evt.body, Boolean(evt.isBase64Encoded)),
    sourceIp: http.sourceIp || null,
  });
}

function ossEvent(evt, fn) {
  const records = (evt.events || []).map((r) => {
    const oss = r.oss || {};
    const obj = oss.object || {};
    return new Record({
      id: (r.responseElements || {}).requestId || null,
      bucket: (oss.bucket || {}).name || null,
      key: obj.key || null,
      size: obj.size === undefined ? null : obj.size,
      action: actionFrom(r.eventName || ""),
      attributes: { event_name: r.eventName, etag: obj.eTag },
      source: "acs:oss",
      raw: r,
    });
  });
  const first = (evt.events || [{}])[0] || {};
  return new Event({
    type: EventType.STORAGE,
    provider: PROVIDER,
    function: fn,
    records,
    source: "acs:oss",
    time: parseTime(first.eventTime),
    raw: evt,
  });
}

function toEvent(native, ctx) {
  const fn = functionName(((ctx || {}).function || {}).name || "");
  const evt = maybeJson(native);
  const wrapped = unwrapEnvelope(evt);
  if (wrapped !== null) {
    const [kind, data, meta] = wrapped;
    return new Event({ type: kind, provider: PROVIDER, function: fn, data, source: meta.source || null, raw: evt });
  }
  if (isObject(evt)) {
    const rc = evt.requestContext;
    if (isObject(rc) && isObject(rc.http)) {
      return new Event({ type: EventType.HTTP, provider: PROVIDER, function: fn, http: toHttp(evt), raw: evt });
    }
    if ("triggerTime" in evt && "triggerName" in evt) {
      const payload = evt.payload;
      const inner = payload ? unwrapEnvelope(payload) : null;
      return new Event({
        type: EventType.SCHEDULE,
        provider: PROVIDER,
        function: fn,
        data: inner ? inner[1] : payload ? maybeJson(payload) : null,
        time: parseTime(evt.triggerTime),
        source: evt.triggerName || null,
        raw: evt,
      });
    }
    const events = evt.events;
    if (Array.isArray(events) && events.length && isObject(events[0]) && "oss" in events[0]) return ossEvent(evt, fn);
    if ("TopicName" in evt && "Message" in evt) {
      const attributes = {};
      for (const [k, v] of Object.entries(evt)) if (k !== "Message") attributes[k] = v;
      const record = new Record({
        id: evt.MessageId || null,
        body: evt.Message,
        attributes,
        source: `${evt.TopicOwner || ""}:${evt.TopicName || ""}`,
        raw: evt,
      });
      return new Event({
        type: EventType.TOPIC,
        provider: PROVIDER,
        function: fn,
        records: [record],
        source: evt.TopicName || null,
        time: parseTime(evt.PublishTime),
        raw: evt,
      });
    }
  }
  return new Event({ type: EventType.INVOKE, provider: PROVIDER, function: fn, data: evt, raw: native });
}

function toContext(ctx, fn) {
  if (!ctx) return new Context({ function: fn, provider: PROVIDER });
  const func = ctx.function || {};
  return new Context({
    requestId: ctx.requestId || "",
    function: fn,
    provider: PROVIDER,
    region: ctx.region || "",
    memoryMb: func.memory ? Number(func.memory) : null,
    deadline: func.timeout ? Date.now() / 1000 + Number(func.timeout) : null,
    raw: ctx,
  });
}

function toNative(result, event) {
  if (event.http) {
    const { status, headers, body, isBase64 } = result.renderForGateway();
    const cookies = result.cookies || [];
    if (cookies.length) headers["set-cookie"] = cookies.length === 1 ? cookies[0] : cookies.join(", ");
    return { statusCode: status, headers, body, isBase64Encoded: isBase64 };
  }
  return result;
}

/** FC 3.0 entrypoint - the generated `index.handler` points here. */
async function handler(native, ctx) {
  const event = toEvent(native, ctx);
  const context = toContext(ctx, event.function);
  return toNative(await execute(event, context), event);
}

module.exports = { PROVIDER, toEvent, toContext, toNative, handler };
