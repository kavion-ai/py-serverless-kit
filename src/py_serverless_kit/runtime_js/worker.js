"use strict";
/**
 * JSON-lines worker: lets a Python process (the on-prem host, `pskit dev`,
 * `pskit invoke`) run Node.js functions. See deploy_docs/NODE_RUNTIME.md.
 *
 *   node pskit_runtime/worker.js          (cwd = bundle root, or set PSKIT_BUNDLE_ROOT)
 *
 * stdin:  {"id", "function", "event": <portable event>, "context": {...}}  or  {"id", "op": "ping"}
 * stdout: {"id", "ok": true, "kind": "http"|"batch"|"value"|"pong", ...}  or  {"id", "ok": false, "error": {...}}
 * stderr: logs (the runtime's JSON lines, console output of handlers)
 *
 * Requests run concurrently. On stdin EOF the worker finishes in-flight requests and exits 0.
 */

const readline = require("readline");

// stdout carries the protocol: everything else written to it (logs, console.log of handlers) goes to stderr.
const protocolWrite = process.stdout.write.bind(process.stdout);

function redirectStdout() {
  process.stdout.write = function redirected(chunk, encoding, callback) {
    return process.stderr.write(chunk, encoding, callback);
  };
}

const { Context } = require("./context");
const { execute } = require("./dispatch");
const { errorName, errorText } = require("./errors");
const { eventFromWire } = require("./event");
const { getLogger } = require("./log");
const { isBatchResult } = require("./batch");
const { dumps, isResponse, toResponse } = require("./response");

const log = getLogger("pskit.worker");

function send(message) {
  protocolWrite(dumps(message) + "\n");
}

function errorPayload(err) {
  return {
    type: errorName(err),
    message: errorText(err),
    stack: err && err.stack ? String(err.stack) : "",
  };
}

/** Turn a dispatcher result into a protocol response (without the id). */
function encodeResult(event, result) {
  if (event.http || isResponse(result)) {
    const resp = isResponse(result) ? result : toResponse(result);
    const rendered = resp.render();
    return {
      ok: true,
      kind: "http",
      status: rendered.status,
      headers: rendered.headers,
      cookies: resp.cookies || [],
      body_b64: rendered.body.toString("base64"),
    };
  }
  if (isBatchResult(result)) return { ok: true, kind: "batch", failed: result.failed.slice() };
  return { ok: true, kind: "value", value: result === undefined ? null : JSON.parse(dumps(result)) };
}

async function handle(request) {
  const id = request.id === undefined ? null : request.id;
  if (request.op === "ping") return { id, ok: true, kind: "pong" };
  try {
    const event = eventFromWire(request.event || {});
    const c = request.context || {};
    const context = new Context({
      requestId: c.request_id || undefined,
      function: c.function || request.function || event.function || "",
      provider: c.provider || event.provider || "local",
      memoryMb: c.memory_mb === undefined ? null : c.memory_mb,
      deadline: c.deadline === undefined ? null : c.deadline,
    });
    if (!event.function) event.function = request.function || "";
    const result = await execute(event, context, request.function || undefined);
    return Object.assign({ id }, encodeResult(event, result));
  } catch (err) {
    return { id, ok: false, error: errorPayload(err) };
  }
}

function main() {
  redirectStdout();
  const inFlight = new Set();
  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity, terminal: false });
  rl.on("line", (line) => {
    if (!line.trim()) return;
    let request;
    try {
      request = JSON.parse(line);
    } catch (err) {
      send({ id: null, ok: false, error: { type: "ProtocolError", message: `invalid JSON request: ${err.message}`, stack: "" } });
      return;
    }
    const job = handle(request)
      .then(send, (err) => send({ id: request.id === undefined ? null : request.id, ok: false, error: errorPayload(err) }))
      .finally(() => inFlight.delete(job));
    inFlight.add(job);
  });
  rl.on("close", async () => {
    while (inFlight.size) await Promise.allSettled(Array.from(inFlight));
    process.exit(0);
  });
  process.on("unhandledRejection", (reason) => {
    log.error("unhandled promise rejection in a handler", {}, reason instanceof Error ? reason : new Error(String(reason)));
  });
  process.on("uncaughtException", (err) => {
    log.error("uncaught exception in a handler", {}, err);
  });
}

if (require.main === module) main();

module.exports = { handle, encodeResult };
