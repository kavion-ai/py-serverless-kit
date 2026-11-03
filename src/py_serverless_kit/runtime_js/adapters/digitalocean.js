"use strict";
/**
 * DigitalOcean Functions adapter (port of runtime/adapters/digitalocean.py), `main(event, context)`.
 *
 * Web functions deployed with `web: raw` receive `event.http` with `method`, `path`,
 * `headers`, `queryString`, `body` and `isBase64Encoded`. Scheduled triggers deliver
 * their `withBody` payload, which the CLI fills with the `__pskit` envelope.
 */

const { Context } = require("../context");
const { Event, EventType, Headers, HttpRequest } = require("../event");
const { dumps } = require("../response");
const { functionName, unwrapEnvelope } = require("./base");
const { decodeBody, eventFromRequest, run } = require("./httpfn");

const PROVIDER = "digitalocean";

function toRequest(event) {
  const http = event.http;
  if (!http || typeof http !== "object" || !http.method) return null;
  const headers = Object.assign({}, http.headers || {});
  let body = http.body;
  if (body === undefined || body === null) {
    // `web: true` (non-raw) merges body params into the event.
    const plain = {};
    for (const [k, v] of Object.entries(event)) if (k !== "http" && !k.startsWith("__ow_")) plain[k] = v;
    body = Object.keys(plain).length ? dumps(plain) : null;
  }
  const isB64 = http.isBase64Encoded;
  const multi = {};
  for (const [k, v] of new URLSearchParams(String(http.queryString || ""))) (multi[k] = multi[k] || []).push(v);
  const query = {};
  for (const [k, v] of Object.entries(multi)) query[k] = v[v.length - 1];
  const forwarded = String(headers["x-forwarded-for"] || "").split(",")[0].trim();
  return new HttpRequest({
    method: String(http.method),
    path: http.path || "/",
    headers: new Headers(headers),
    query,
    multiQuery: multi,
    body: decodeBody(body, headers, isB64 === undefined || isB64 === null ? false : Boolean(isB64)),
    sourceIp: forwarded || null,
  });
}

function toEvent(event, fn) {
  const req = toRequest(event);
  if (req !== null) return eventFromRequest(req, PROVIDER, fn, event);
  const wrapped = unwrapEnvelope(event);
  if (wrapped !== null) {
    const [kind, data, meta] = wrapped;
    return new Event({ type: kind, provider: PROVIDER, function: fn, data, source: meta.source || null, raw: event });
  }
  return new Event({ type: EventType.INVOKE, provider: PROVIDER, function: fn, data: event, raw: event });
}

function toContext(ctx, fn) {
  const remaining = ctx && typeof ctx.getRemainingTimeInMillis === "function" ? () => ctx.getRemainingTimeInMillis() : undefined;
  return new Context({
    requestId: String((ctx && (ctx.activationId || ctx.activation_id || ctx.requestId)) || "") || undefined,
    function: fn,
    provider: PROVIDER,
    deadline: remaining ? Date.now() / 1000 + remaining() / 1000 : null,
    raw: ctx || null,
    remaining,
  });
}

/** DigitalOcean entrypoint (`main` in project.yml). */
async function main(event, context) {
  const e = event || {};
  const fn = functionName();
  const { status, headers, body } = await run(toEvent(e, fn), toContext(context, fn));
  return { statusCode: status, headers, body };
}

module.exports = { PROVIDER, toRequest, toEvent, toContext, main };
