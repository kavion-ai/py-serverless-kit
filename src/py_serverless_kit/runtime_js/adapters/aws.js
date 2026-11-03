"use strict";
/**
 * AWS Lambda adapter (port of runtime/adapters/aws.py).
 *
 * Handles API Gateway HTTP API (payload v2), REST API / ALB (payload v1),
 * Lambda Function URLs, SQS, SNS, S3, EventBridge, Step Functions and direct
 * invocation. The generated `pskit_entry.js` re-exports `handler`.
 */

const { Context } = require("../context");
const { execute } = require("../dispatch");
const { Event, EventType, Headers, HttpRequest, Record, parseTime } = require("../event");
const { isBatchResult } = require("../batch");
const { toResponse } = require("../response");
const { actionFrom, functionName, maybeJson, unwrapEnvelope } = require("./base");

const PROVIDER = "aws";

function httpV2(evt) {
  const rc = evt.requestContext || {};
  const http = rc.http || {};
  const headers = Object.assign({}, evt.headers || {});
  if (Array.isArray(evt.cookies) && evt.cookies.length) headers.cookie = evt.cookies.join("; ");
  const query = Object.assign({}, evt.queryStringParameters || {});
  const multi = {};
  for (const [k, v] of Object.entries(query)) multi[k] = String(v).split(",");
  return new HttpRequest({
    method: http.method || "GET",
    path: evt.rawPath || http.path || "/",
    headers: new Headers(headers),
    query,
    multiQuery: multi,
    pathParams: Object.assign({}, evt.pathParameters || {}),
    body: HttpRequest.decodeBody(evt.body, Boolean(evt.isBase64Encoded)),
    sourceIp: http.sourceIp || null,
    route: String(evt.routeKey || "").split(" ").slice(1).join(" ") || null,
  });
}

function httpV1(evt) {
  const rc = evt.requestContext || {};
  const multiHeaders = evt.multiValueHeaders || {};
  const headers = Object.keys(multiHeaders).length ? Object.assign({}, multiHeaders) : Object.assign({}, evt.headers || {});
  const multiQuery = {};
  for (const [k, v] of Object.entries(evt.multiValueQueryStringParameters || {})) multiQuery[k] = Array.from(v);
  let query = Object.assign({}, evt.queryStringParameters || {});
  if (!Object.keys(query).length && Object.keys(multiQuery).length) {
    query = {};
    for (const [k, v] of Object.entries(multiQuery)) query[k] = v[v.length - 1];
  }
  const fallbackMulti = {};
  for (const [k, v] of Object.entries(query)) fallbackMulti[k] = [v];
  return new HttpRequest({
    method: evt.httpMethod || "GET",
    path: evt.path || "/",
    headers: new Headers(headers),
    query,
    multiQuery: Object.keys(multiQuery).length ? multiQuery : fallbackMulti,
    pathParams: Object.assign({}, evt.pathParameters || {}),
    body: HttpRequest.decodeBody(evt.body, Boolean(evt.isBase64Encoded)),
    sourceIp: (rc.identity || {}).sourceIp || null,
    route: evt.resource || null,
  });
}

function decodeS3Key(key) {
  try {
    return decodeURIComponent(String(key || "").replace(/\+/g, " "));
  } catch (err) {
    return String(key || "");
  }
}

function recordsEvent(evt) {
  const records = evt.Records;
  if (!Array.isArray(records) || !records.length) return null;
  const first = records[0];
  const source = first.eventSource || first.EventSource || "";
  if (source === "aws:sqs") {
    const out = records.map((r) => {
      const attrs = Object.assign({}, r.attributes || {});
      for (const [k, v] of Object.entries(r.messageAttributes || {})) attrs[k] = (v || {}).stringValue;
      return new Record({ id: r.messageId, body: r.body, attributes: attrs, source: r.eventSourceARN, raw: r });
    });
    return new Event({ type: EventType.QUEUE, provider: PROVIDER, records: out, source: first.eventSourceARN, raw: evt });
  }
  if (source === "aws:sns") {
    const out = records.map((r) => {
      const sns = r.Sns || {};
      const attrs = {};
      for (const [k, v] of Object.entries(sns.MessageAttributes || {})) attrs[k] = (v || {}).Value;
      return new Record({ id: sns.MessageId, body: sns.Message, attributes: attrs, source: sns.TopicArn, raw: r });
    });
    const sns = first.Sns || {};
    return new Event({
      type: EventType.TOPIC,
      provider: PROVIDER,
      records: out,
      source: sns.TopicArn,
      time: parseTime(sns.Timestamp),
      raw: evt,
    });
  }
  if (source === "aws:s3") {
    const out = records.map((r) => {
      const s3 = r.s3 || {};
      const obj = s3.object || {};
      return new Record({
        id: obj.sequencer,
        bucket: (s3.bucket || {}).name,
        key: decodeS3Key(obj.key),
        size: obj.size,
        action: actionFrom(r.eventName || ""),
        attributes: { etag: obj.eTag, event_name: r.eventName },
        source: "aws:s3",
        raw: r,
      });
    });
    return new Event({
      type: EventType.STORAGE,
      provider: PROVIDER,
      records: out,
      source: "aws:s3",
      time: parseTime(first.eventTime),
      raw: evt,
    });
  }
  return null;
}

function toEvent(evt, ctx) {
  const fn = functionName((ctx && ctx.functionName) || "");
  const wrapped = unwrapEnvelope(evt);
  if (wrapped) {
    return new Event({ type: wrapped[0], provider: PROVIDER, function: fn, data: wrapped[1], source: (wrapped[2].source || null), raw: evt });
  }
  if (evt && typeof evt === "object" && !Array.isArray(evt)) {
    const rc = evt.requestContext;
    if (rc && typeof rc === "object" && rc.http && typeof rc.http === "object") {
      return new Event({ type: EventType.HTTP, provider: PROVIDER, function: fn, http: httpV2(evt), raw: evt });
    }
    if ("httpMethod" in evt) {
      return new Event({ type: EventType.HTTP, provider: PROVIDER, function: fn, http: httpV1(evt), raw: evt });
    }
    const batch = recordsEvent(evt);
    if (batch) {
      batch.function = fn;
      return batch;
    }
    if (evt.source === "aws.events" || evt["detail-type"] === "Scheduled Event") {
      return new Event({
        type: EventType.SCHEDULE,
        provider: PROVIDER,
        function: fn,
        data: evt.detail === undefined ? null : evt.detail,
        time: parseTime(evt.time),
        source: evt.source,
        raw: evt,
      });
    }
  }
  return new Event({ type: EventType.INVOKE, provider: PROVIDER, function: fn, data: maybeJson(evt), raw: evt });
}

function toContext(ctx, fn) {
  if (!ctx) return new Context({ function: fn, provider: PROVIDER });
  const remaining = typeof ctx.getRemainingTimeInMillis === "function" ? () => ctx.getRemainingTimeInMillis() : null;
  const memory = ctx.memoryLimitInMB;
  return new Context({
    requestId: ctx.awsRequestId || "",
    function: fn,
    provider: PROVIDER,
    memoryMb: memory ? Number(memory) : null,
    deadline: remaining ? Date.now() / 1000 + remaining() / 1000 : null,
    raw: ctx,
    remaining: remaining || undefined,
  });
}

function toNative(result, event) {
  if (event.http) {
    const resp = toResponse(result);
    const { status, headers, body, isBase64 } = resp.renderForGateway();
    const out = { statusCode: status, headers, body, isBase64Encoded: isBase64 };
    if (resp.cookies && resp.cookies.length) {
      if ((event.raw || {}).version === "2.0") out.cookies = Array.from(resp.cookies);
      else out.multiValueHeaders = { "set-cookie": Array.from(resp.cookies) };
    }
    return out;
  }
  if (isBatchResult(result)) {
    return { batchItemFailures: result.failed.map((id) => ({ itemIdentifier: id })) };
  }
  return result === undefined ? null : result;
}

/** Lambda entrypoint - `pskit_entry.handler` points here. */
async function handler(evt, ctx) {
  const event = toEvent(evt, ctx);
  const context = toContext(ctx, event.function);
  const result = await execute(event, context);
  return toNative(result, event);
}

module.exports = { PROVIDER, toEvent, toContext, toNative, handler };
