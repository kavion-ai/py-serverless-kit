"use strict";
/**
 * IBM Cloud Code Engine functions adapter (port of runtime/adapters/ibm.py).
 *
 * Code Engine calls `main(params)`; HTTP request data arrives in `__ce_*` keys
 * (`__ow_*` from the older Cloud Functions / OpenWhisk platform is accepted too)
 * and the function returns `{statusCode, headers, body}`.
 */

const crypto = require("crypto");
const { Context } = require("../context");
const { Event, EventType, Headers, HttpRequest } = require("../event");
const { dumps } = require("../response");
const { functionName, unwrapEnvelope } = require("./base");
const { decodeBody, eventFromRequest, run } = require("./httpfn");

const PROVIDER = "ibm";
const PREFIXES = ["__ce_", "__ow_"];

function get(params, key) {
  for (const prefix of PREFIXES) if (Object.prototype.hasOwnProperty.call(params, prefix + key)) return params[prefix + key];
  return undefined;
}

function parseQuery(raw) {
  const multi = {};
  if (raw && typeof raw === "object") {
    for (const [k, v] of Object.entries(raw)) multi[k] = Array.isArray(v) ? v.map(String) : [String(v)];
  } else if (typeof raw === "string" && raw) {
    for (const [k, v] of new URLSearchParams(raw.replace(/^\?/, ""))) (multi[k] = multi[k] || []).push(v);
  }
  return multi;
}

function toRequest(params) {
  const method = get(params, "method");
  if (!method) return null;
  const headers = Object.assign({}, get(params, "headers") || {});
  let body = get(params, "body");
  if (body === undefined || body === null) {
    // Code Engine merges JSON bodies into params; rebuild it from the plain keys.
    const plain = {};
    for (const [k, v] of Object.entries(params)) if (!PREFIXES.some((p) => k.startsWith(p))) plain[k] = v;
    body = Object.keys(plain).length ? dumps(plain) : null;
  }
  const multi = parseQuery(get(params, "query"));
  const query = {};
  for (const [k, v] of Object.entries(multi)) if (v.length) query[k] = v[v.length - 1];
  const forwarded = String(headers["x-forwarded-for"] || "").split(",")[0].trim();
  return new HttpRequest({
    method: String(method),
    path: get(params, "path") || "/",
    headers: new Headers(headers),
    query,
    multiQuery: multi,
    body: decodeBody(body, headers),
    sourceIp: forwarded || null,
  });
}

function headersId(params) {
  const headers = get(params, "headers") || {};
  for (const key of ["x-request-id", "X-Request-Id", "x-ce-request-id"]) if (headers[key]) return String(headers[key]);
  return crypto.randomUUID();
}

function toEvent(params, fn) {
  const req = toRequest(params);
  if (req === null) {
    // Direct invocation without HTTP metadata: params are the payload.
    const wrapped = unwrapEnvelope(params);
    if (wrapped !== null) return new Event({ type: wrapped[0], provider: PROVIDER, function: fn, data: wrapped[1], raw: params });
    return new Event({ type: EventType.INVOKE, provider: PROVIDER, function: fn, data: params, raw: params });
  }
  return eventFromRequest(req, PROVIDER, fn, params);
}

/** Code Engine entrypoint (`code_main: main`). */
async function main(params) {
  const p = params || {};
  const fn = functionName();
  const event = toEvent(p, fn);
  const context = new Context({
    requestId: process.env.CE_REQUEST_ID || headersId(p),
    function: fn,
    provider: PROVIDER,
    raw: p,
  });
  const { status, headers, body } = await run(event, context);
  return { statusCode: status, headers, body };
}

module.exports = { PROVIDER, toRequest, toEvent, main };
