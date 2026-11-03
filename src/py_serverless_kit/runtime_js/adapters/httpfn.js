"use strict";
/**
 * Shared logic for providers where every invocation arrives as an HTTP-ish
 * request (IBM Code Engine, DigitalOcean web functions, Cloudflare Workers,
 * OCI behind API Gateway). Port of runtime/adapters/_httpfn.py.
 *
 * A request whose JSON body carries the `__pskit` envelope is a non-HTTP event
 * (invoke(), workflow task, scheduler with input): the handler result is
 * returned as JSON 200, and failures as JSON 500 `{"errorType", "cause"}`,
 * the same contract the GCP adapter uses.
 */

const { execute } = require("../dispatch");
const { errorName, errorText } = require("../errors");
const { Event, EventType } = require("../event");
const { dumps, isResponse } = require("../response");
const { maybeJson, unwrapEnvelope } = require("./base");

/** @returns {Event} */
function eventFromRequest(req, provider, functionName, raw = null) {
  if (req.method === "POST" && req.body.subarray(0, 1).toString() === "{") {
    const wrapped = unwrapEnvelope(req.body);
    if (wrapped !== null) {
      const [kind, data, meta] = wrapped;
      return new Event({ type: kind, provider, function: functionName, data, source: meta.source || null, raw });
    }
  }
  return new Event({ type: EventType.HTTP, provider, function: functionName, http: req, raw });
}

function errorBody(err) {
  return { errorType: errorName(err), cause: errorText(err) };
}

/** @returns {{status: number, headers: Record<string,string>, body: string, isBase64: boolean}} */
function resultToHttp(event, result) {
  if (isResponse(result)) return result.renderForGateway();
  return { status: 200, headers: { "content-type": "application/json" }, body: dumps(result), isBase64: false };
}

/** Execute and always resolve to an HTTP-shaped result `{status, headers, body, isBase64}`. */
async function run(event, context) {
  if (event.http) return (await execute(event, context)).renderForGateway();
  let result;
  try {
    result = await execute(event, context);
  } catch (err) {
    return { status: 500, headers: { "content-type": "application/json" }, body: dumps(errorBody(err)), isBase64: false };
  }
  return resultToHttp(event, result);
}

/** Decode a body that may be base64 when the content type is binary. */
function decodeBody(body, headers, isBase64 = null) {
  if (body === null || body === undefined) return Buffer.alloc(0);
  if (Buffer.isBuffer(body)) return body;
  if (typeof body === "object") return Buffer.from(dumps(body), "utf8");
  const text = String(body);
  let b64 = isBase64;
  if (b64 === null || b64 === undefined) {
    let ctype = "";
    for (const [k, v] of Object.entries(headers || {})) if (String(k).toLowerCase() === "content-type") ctype = String(v).toLowerCase();
    const textual = !ctype || ctype.startsWith("text/") || ctype.includes("json") || ctype.includes("xml") || ctype.includes("form");
    b64 = !textual;
  }
  if (b64) {
    if (/^[A-Za-z0-9+/]*={0,2}$/.test(text.replace(/\s/g, "")) && text.replace(/\s/g, "").length % 4 === 0) {
      return Buffer.from(text, "base64");
    }
    return Buffer.from(text, "utf8");
  }
  return Buffer.from(text, "utf8");
}

function jsonOrText(text) {
  return maybeJson(text);
}

module.exports = { eventFromRequest, errorBody, resultToHttp, run, decodeBody, jsonOrText };
