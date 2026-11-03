"use strict";
/**
 * Cloudflare Workers adapter (JavaScript; port of runtime/adapters/cloudflare.py).
 *
 * The generated entry `_pskit_cf/<fn>.mjs` is bundled with esbuild into one ES module and
 * does `export default worker({function, manifest, schedules, modules})`:
 *
 * - `manifest`  the parsed pskit_manifest.json (Workers have no file system to read it from);
 * - `schedules` {cron expression: schedule input};
 * - `modules`   {"src.handlers": <module namespace>} - handler modules imported statically,
 *               because a bundle can't import a file by a computed path.
 *
 * String bindings (`plain_text` environment variables) are copied into `process.env`
 * on every invocation. A POST whose JSON body carries the `__pskit` envelope is run
 * as a non-HTTP event and answered with JSON (500 `{"errorType", "cause"}` on failure).
 */

const { Context } = require("../context");
const { errorName, errorText } = require("../errors");
const dispatch = require("../dispatch");
const { Event, EventType, Headers, HttpRequest, parseTime } = require("../event");
const { setManifest } = require("../manifest");
const { dumps, toResponse } = require("../response");
const { unwrapEnvelope } = require("./base");

const PROVIDER = "cloudflare";
const JSON_TYPE = "application/json";

function processEnv() {
  if (typeof process === "undefined") globalThis.process = { env: {} };
  if (!process.env) process.env = {};
  return process.env;
}

/** Copy string bindings (environment variables) into process.env. */
function applyEnv(env, fn) {
  const target = processEnv();
  for (const [k, v] of Object.entries(env || {})) if (typeof v === "string") target[k] = v;
  target.PSKIT_FUNCTION = fn;
}

function registerModules(modules) {
  if (typeof dispatch.registerModules === "function") dispatch.registerModules(modules);
  else globalThis.__PSKIT_MODULES__ = Object.assign(globalThis.__PSKIT_MODULES__ || {}, modules);
}

async function toRequest(request) {
  const url = new URL(request.url);
  const method = String(request.method || "GET").toUpperCase();
  const headers = Array.from(request.headers.entries());
  const body = method === "GET" || method === "HEAD" ? Buffer.alloc(0) : Buffer.from(await request.arrayBuffer());
  const multi = {};
  for (const [k, v] of url.searchParams.entries()) (multi[k] = multi[k] || []).push(v);
  const query = {};
  for (const [k, v] of Object.entries(multi)) query[k] = v[v.length - 1];
  return new HttpRequest({
    method,
    path: url.pathname || "/",
    headers: new Headers(headers),
    query,
    multiQuery: multi,
    body,
    sourceIp: request.headers.get("cf-connecting-ip") || null,
  });
}

function jsonResponse(status, payload) {
  return new Response(dumps(payload), { status, headers: { "content-type": JSON_TYPE } });
}

async function fetchHandler(request, env, fn) {
  applyEnv(env, fn);
  const req = await toRequest(request);
  const context = new Context({ requestId: request.headers.get("cf-ray") || undefined, function: fn, provider: PROVIDER, raw: env });
  const wrapped = req.method === "POST" && req.body[0] === 0x7b ? unwrapEnvelope(req.body) : null;
  if (wrapped) {
    const event = new Event({ type: wrapped[0], provider: PROVIDER, function: fn, data: wrapped[1], source: (wrapped[2].source || null), raw: request });
    try {
      const result = await dispatch.execute(event, context, fn);
      return jsonResponse(200, result === undefined ? null : result);
    } catch (err) {
      return jsonResponse(500, { errorType: errorName(err), cause: errorText(err) });
    }
  }
  const event = new Event({ type: EventType.HTTP, provider: PROVIDER, function: fn, http: req, raw: request });
  const resp = toResponse(await dispatch.execute(event, context, fn));
  const { status, headers, body } = resp.render();
  const out = new globalThis.Headers();
  for (const [k, v] of Object.entries(headers)) out.set(k, v);
  for (const c of resp.cookies || []) out.append("set-cookie", c);
  const noBody = status === 204 || status === 304 || req.method === "HEAD";
  return new Response(noBody ? null : body, { status, headers: out });
}

async function scheduledHandler(controller, env, fn, schedules) {
  applyEnv(env, fn);
  const cron = String((controller && controller.cron) || "");
  const event = new Event({
    type: EventType.SCHEDULE,
    provider: PROVIDER,
    function: fn,
    data: Object.prototype.hasOwnProperty.call(schedules, cron) ? schedules[cron] : null,
    time: parseTime(controller && controller.scheduledTime),
    source: cron || null,
    raw: controller,
  });
  return dispatch.execute(event, new Context({ function: fn, provider: PROVIDER, raw: env }), fn);
}

/** The Worker's default export: `{fetch, scheduled}` for one logical function. */
function worker({ function: fn, manifest = null, schedules = {}, modules = {} } = {}) {
  if (manifest) setManifest(manifest);
  registerModules(modules);
  return {
    fetch: (request, env, ctx) => fetchHandler(request, env, fn),
    scheduled: (controller, env, ctx) => {
      const run = scheduledHandler(controller, env, fn, schedules || {});
      if (ctx && typeof ctx.waitUntil === "function") ctx.waitUntil(run);
      return run;
    },
  };
}

module.exports = { PROVIDER, worker, toRequest, fetchHandler, scheduledHandler, applyEnv };
