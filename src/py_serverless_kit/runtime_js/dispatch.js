"use strict";
/**
 * Calls the user's handler with a normalized event and normalizes the result
 * (port of runtime/dispatch.py). Every adapter goes through `execute`, so
 * error mapping, CORS, routing and logging are identical on every cloud.
 */

const { isBatchResult } = require("./batch");
const { HandlerNotFound, isHttpError, errorName, errorText } = require("./errors");
const { getLogger } = require("./log");
const { bundleRoot, resolveFunction } = require("./manifest");
const { Response, toResponse } = require("./response");
const { matchPath, methodMatches } = require("./routing");
const { nodeModule, nowMs, round2 } = require("./util");

const handlers = new Map();
// Modules registered in memory: platforms without a filesystem (Cloudflare Workers) or bundled builds.
const registry = new Map();
const log = getLogger("pskit.runtime");

const DEFAULT_CORS = Object.freeze({
  origins: ["*"],
  methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
  headers: ["Content-Type", "Authorization", "X-Requested-With"],
  expose_headers: [],
  allow_credentials: false,
  max_age: 600,
});
const EXTENSIONS = [".js", ".mjs", ".cjs"];
// Handlers inside the runtime itself (e.g. `pskit_runtime.workflow.orchestrate`) load this copy.
const RUNTIME_PREFIXES = new Set(["pskit_runtime", "pskit"]);

// Runtime modules a handler string can name, loaded with static requires so bundlers include them.
const RUNTIME_MODULES = {
  workflow: () => require("./workflow"),
  index: () => require("./index"),
};

/** Registry key of a module: `src/handlers` (dots or slashes in, no extension). */
function moduleKey(name) {
  return String(name)
    .replace(/\\/g, "/")
    .replace(/^\.?\/+/, "")
    .replace(/\.(m|c)?[jt]s$/, "")
    .replace(/\./g, "/");
}

/**
 * Register handler modules in memory, keyed by module path:
 * `registerModules({"src/handlers": ns})` (dotted keys such as `"src.handlers"` work too).
 * Consulted before the filesystem; required where there is none (Cloudflare Workers).
 */
function registerModules(modules) {
  for (const [name, ns] of Object.entries(modules || {})) registry.set(moduleKey(name), ns);
}

function registered(moduleName) {
  const key = moduleKey(moduleName);
  if (registry.has(key)) return registry.get(key);
  const global = typeof globalThis !== "undefined" ? globalThis.__PSKIT_MODULES__ : undefined;
  if (global && typeof global === "object") {
    for (const [name, ns] of Object.entries(global)) if (moduleKey(name) === key) return ns;
  }
  const parts = moduleName.split(".");
  if (RUNTIME_PREFIXES.has(parts[0])) {
    const load = RUNTIME_MODULES[parts.length > 1 ? parts.slice(1).join("/") : "index"];
    if (load) return load();
  }
  return undefined;
}

function moduleFile(moduleName) {
  const fs = nodeModule("fs");
  const path = nodeModule("path");
  if (!fs || !path) return undefined;
  const parts = moduleName.split(".");
  let base;
  if (RUNTIME_PREFIXES.has(parts[0])) {
    if (typeof __dirname === "undefined") return undefined;
    base = path.join(__dirname, ...(parts.length > 1 ? parts.slice(1) : ["index"]));
  } else {
    const root = bundleRoot();
    if (!root) return undefined;
    base = path.join(root, ...parts);
  }
  const options = EXTENSIONS.map((ext) => base + ext).concat(EXTENSIONS.map((ext) => path.join(base, "index" + ext)));
  return options.find((file) => {
    try {
      return fs.statSync(file).isFile();
    } catch (err) {
      return false;
    }
  });
}

async function loadModule(file) {
  if (!file.endsWith(".mjs")) {
    try {
      return nodeModule(file, true);
    } catch (err) {
      if (!err || !["ERR_REQUIRE_ESM", "ERR_REQUIRE_ASYNC_MODULE"].includes(err.code)) throw err;
    }
  }
  const url = nodeModule("url");
  return import(url ? url.pathToFileURL(file).href : file);
}

function lookup(target, attr) {
  let current = target;
  for (const part of attr.split(".")) {
    if (current === null || current === undefined) return undefined;
    current = current[part];
  }
  return current;
}

/**
 * Import `package.module.function` (or `package.module:function`) from the bundle.
 * Folders are dots: `src.handlers.hello` → `src/handlers.js` export `hello`.
 * @returns {Promise<Function>}
 */
async function resolveHandler(handlerPath) {
  const cached = handlers.get(handlerPath);
  if (cached) return cached;
  let moduleName;
  let attr;
  if (handlerPath.includes(":")) {
    const idx = handlerPath.indexOf(":");
    moduleName = handlerPath.slice(0, idx);
    attr = handlerPath.slice(idx + 1);
  } else {
    const idx = handlerPath.lastIndexOf(".");
    moduleName = idx >= 0 ? handlerPath.slice(0, idx) : "";
    attr = idx >= 0 ? handlerPath.slice(idx + 1) : handlerPath;
  }
  if (!moduleName || !attr) {
    throw new HandlerNotFound(`Handler '${handlerPath}' must look like 'package.module.function'`);
  }
  let mod = registered(moduleName);
  if (mod === undefined) {
    const file = moduleFile(moduleName);
    if (!file) {
      throw new HandlerNotFound(
        `Cannot import module '${moduleName}' for handler '${handlerPath}': no ${moduleKey(moduleName)}` +
          `{${EXTENSIONS.join(",")}} under ${bundleRoot() || "<no filesystem>"} and no registered module`,
      );
    }
    try {
      mod = await loadModule(file);
    } catch (err) {
      if (err && err.code === "MODULE_NOT_FOUND") {
        throw new HandlerNotFound(`Cannot import module '${moduleName}' for handler '${handlerPath}': ${errorText(err)}`);
      }
      throw err;
    }
  }
  let target = lookup(mod, attr);
  if (target === undefined && mod && mod.default) target = lookup(mod.default, attr);
  if (target === undefined || target === null) {
    throw new HandlerNotFound(`Module '${moduleName}' has no attribute '${attr}'`);
  }
  if (typeof target !== "function") throw new HandlerNotFound(`Handler '${handlerPath}' is not callable`);
  handlers.set(handlerPath, target);
  return target;
}

/** Forget imported handlers (tests, hot reload). */
function clearHandlerCache() {
  handlers.clear();
}

// ---------------------------------------------------------------- routing / CORS

function selectRoute(spec, event) {
  const req = event.http;
  if (!req || !spec.routes.length) return { route: null, early: null };
  let pathMatched = null;
  // Exact matches win over tolerant ones (e.g. GET /hello vs GET /hello/{name}).
  for (const tolerant of [false, true]) {
    for (const route of spec.routes) {
      const params = matchPath(route.path, req.path, { tolerant });
      if (params === null) continue;
      pathMatched = pathMatched || route;
      if (methodMatches(route.method, req.method) || req.method === "OPTIONS") {
        if (!Object.keys(req.pathParams).length) req.pathParams = params;
        req.route = route.path;
        return { route, early: null };
      }
    }
    if (pathMatched !== null) break;
  }
  if (pathMatched !== null) {
    const allowed = Array.from(
      new Set(spec.routes.filter((r) => matchPath(r.path, req.path) !== null).map((r) => String(r.method).toUpperCase())),
    ).sort();
    const resp = Response.json({ error: "Method Not Allowed", status: 405 }, 405, { allow: allowed.join(", ") });
    return { route: pathMatched, early: resp };
  }
  return { route: null, early: null };
}

function corsConfig(route, spec) {
  let cors = route ? route.cors : null;
  if (!route) {
    const found = spec.routes.find((r) => r.cors);
    cors = found ? found.cors : null;
  }
  if (!cors) return null;
  const merged = Object.assign({}, DEFAULT_CORS);
  if (typeof cors === "object") {
    for (const [k, v] of Object.entries(cors)) if (v !== null && v !== undefined) merged[k] = v;
  }
  return merged;
}

function applyCors(resp, cors, origin, preflight) {
  const origins = cors.origins && cors.origins.length ? cors.origins : ["*"];
  let allowOrigin;
  if (origins.includes("*") && !cors.allow_credentials) allowOrigin = "*";
  else if (origin && (origins.includes(origin) || origins.includes("*"))) allowOrigin = origin;
  else return resp;
  const headers = { "access-control-allow-origin": allowOrigin };
  if (allowOrigin !== "*") headers.vary = "Origin";
  if (cors.allow_credentials) headers["access-control-allow-credentials"] = "true";
  if (cors.expose_headers && cors.expose_headers.length) {
    headers["access-control-expose-headers"] = cors.expose_headers.join(", ");
  }
  if (preflight) {
    headers["access-control-allow-methods"] = (cors.methods || []).join(", ");
    headers["access-control-allow-headers"] = (cors.headers || []).join(", ");
    headers["access-control-max-age"] = String(cors.max_age === undefined ? 600 : cors.max_age);
  }
  for (const [k, v] of Object.entries(headers)) if (!(k in resp.headers)) resp.headers[k] = v;
  return resp;
}

// ---------------------------------------------------------------- execution

function errorResponse(err, context) {
  if (isHttpError(err)) return Response.json(err.toBody(), err.status, err.headers);
  const body = { error: "Internal Server Error", status: 500, request_id: context.requestId };
  if (["1", "true", "yes"].includes(String(process.env.PSKIT_DEBUG || "").toLowerCase())) {
    body.detail = `${errorName(err)}: ${errorText(err)}`;
  }
  return Response.json(body, 500);
}

function prepare(event, context, functionName) {
  const prep = { spec: null, route: null, cors: null, early: null, started: nowMs() };
  const spec = resolveFunction(functionName || event.function || null);
  prep.spec = spec;
  event.function = event.function || spec.name;
  context.function = context.function || spec.name;
  if (event.http) {
    const sel = selectRoute(spec, event);
    prep.route = sel.route;
    prep.early = sel.early;
    prep.cors = corsConfig(prep.route, spec);
    if (prep.early === null && prep.cors && event.http.method === "OPTIONS") prep.early = new Response(204, "");
  }
  return prep;
}

function finish(prep, event, context, result, error) {
  const elapsedMs = round2(nowMs() - prep.started);
  if (!event.http) {
    if (error !== null) {
      context.logger.error("handler failed", { event_type: event.type, duration_ms: elapsedMs }, error);
      throw error;
    }
    context.logger.debug("handler ok", { event_type: event.type, duration_ms: elapsedMs });
    // AWS, the local runner and the on-premises host report partial failures.
    // Everywhere else the whole batch must fail so the platform redelivers it.
    if (isBatchResult(result) && !["aws", "local", "onprem"].includes(event.provider)) {
      result.raiseIfFailed();
      return null;
    }
    return result;
  }
  let resp;
  if (error !== null) {
    if (!isHttpError(error) || error.status >= 500) {
      context.logger.error("handler failed", { method: event.http.method, path: event.http.path }, error);
    }
    resp = errorResponse(error, context);
  } else {
    resp = toResponse(result);
  }
  if (prep.cors) applyCors(resp, prep.cors, event.http.headers.get("origin"), event.http.method === "OPTIONS");
  context.logger.info("request", {
    method: event.http.method,
    path: event.http.path,
    status: resp.status,
    duration_ms: elapsedMs,
  });
  return resp;
}

/**
 * Run the handler. HTTP events always resolve to a Response; anything else
 * resolves to the handler's raw result, and errors reject so the platform's
 * retry policy applies.
 * @param {import("./event").Event} event
 * @param {import("./context").Context} context
 * @param {string} [functionName]
 */
async function execute(event, context, functionName) {
  const prep = prepare(event, context, functionName);
  if (prep.early !== null) return finish(prep, event, context, prep.early, null);
  let result;
  try {
    const fn = await resolveHandler(prep.spec.handler);
    result = await fn(event, context);
  } catch (err) {
    return finish(prep, event, context, null, err === null || err === undefined ? new Error(String(err)) : err);
  }
  return finish(prep, event, context, result, null);
}

function isHttp(event) {
  return event.type === "http";
}

/** Forget registered modules (tests). */
function clearModuleRegistry() {
  registry.clear();
}

module.exports = {
  execute,
  resolveHandler,
  registerModules,
  clearModuleRegistry,
  clearHandlerCache,
  isHttp,
  DEFAULT_CORS,
  log,
};
