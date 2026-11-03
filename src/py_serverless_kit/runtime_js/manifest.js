"use strict";
/**
 * Reads `pskit_manifest.json` (port of runtime/manifest.py): the per-bundle
 * description of every function, written by the CLI into the bundle root.
 *
 * Where there is no filesystem (Cloudflare Workers) the manifest is registered
 * instead: `registerManifest(obj)` or `globalThis.__PSKIT_MANIFEST__`.
 */

const { LookupError } = require("./errors");
const { env, nodeModule } = require("./util");

const MANIFEST_FILE = "pskit_manifest.json";
const PARSED = Symbol("pskit.manifest");

/**
 * Bundle root: `$PSKIT_BUNDLE_ROOT`, else the folder holding this runtime
 * (`<bundle>/pskit_runtime`), or "" where there is no filesystem.
 */
function bundleRoot() {
  const path = nodeModule("path");
  const configured = env().PSKIT_BUNDLE_ROOT;
  if (configured) return path ? path.resolve(configured) : configured;
  if (!path || typeof __dirname === "undefined") return "";
  return path.dirname(__dirname);
}

function fromDict(raw) {
  const src = raw || {};
  const functions = {};
  for (const [name, spec] of Object.entries(src.functions || {})) {
    functions[name] = {
      name,
      handler: spec.handler,
      routes: (spec.routes || []).map((r) => ({ method: r.method, path: r.path, cors: r.cors === undefined ? null : r.cors })),
      timeout: spec.timeout === undefined ? null : spec.timeout,
      memory: spec.memory === undefined ? null : spec.memory,
      resourceName: spec.resource_name === undefined ? null : spec.resource_name,
    };
  }
  const manifest = {
    service: src.service || "",
    stage: src.stage || "",
    provider: src.provider || "local",
    region: src.region || "",
    functions,
    workflows: src.workflows || {},
  };
  Object.defineProperty(manifest, PARSED, { value: true });
  return manifest;
}

let cache = null;

function candidates() {
  const path = nodeModule("path");
  if (!path) return [];
  const vars = env();
  const out = [];
  if (vars.PSKIT_MANIFEST) out.push(vars.PSKIT_MANIFEST);
  const root = bundleRoot();
  if (root) out.push(path.join(root, MANIFEST_FILE));
  for (const name of ["LAMBDA_TASK_ROOT", "FC_FUNC_CODE_PATH", "RUNTIME_CODE_ROOT"]) {
    if (vars[name]) out.push(path.join(vars[name], MANIFEST_FILE));
  }
  if (typeof process !== "undefined" && typeof process.cwd === "function") {
    try {
      out.push(path.join(process.cwd(), MANIFEST_FILE));
    } catch (err) {
      // no working directory (sandboxed runtimes)
    }
  }
  return out;
}

function loadManifest(reload = false) {
  if (cache !== null && !reload) return cache;
  const global = typeof globalThis !== "undefined" ? globalThis.__PSKIT_MANIFEST__ : undefined;
  if (global && typeof global === "object") {
    cache = global[PARSED] ? global : fromDict(global);
    return cache;
  }
  const fs = nodeModule("fs");
  for (const file of fs ? candidates() : []) {
    let text;
    try {
      if (!fs.statSync(file).isFile()) continue;
      text = fs.readFileSync(file, "utf8");
    } catch (err) {
      continue;
    }
    cache = fromDict(JSON.parse(text));
    return cache;
  }
  const vars = env();
  cache = fromDict({ service: vars.PSKIT_SERVICE || "", stage: vars.PSKIT_STAGE || "", provider: vars.PSKIT_PROVIDER || "local" });
  return cache;
}

/** Install a manifest programmatically (raw dict, or null to reset). */
function setManifest(manifest) {
  if (manifest === null || manifest === undefined) cache = null;
  else cache = manifest[PARSED] ? manifest : fromDict(manifest);
}

/** Same as setManifest: the manifest of a bundle without a filesystem (Cloudflare Workers). */
function registerManifest(manifest) {
  setManifest(manifest);
}

/** The spec of function `name` (default `$PSKIT_FUNCTION`). */
function resolveFunction(name) {
  const manifest = loadManifest();
  const vars = env();
  const fn = name || vars.PSKIT_FUNCTION || "";
  if (fn && Object.prototype.hasOwnProperty.call(manifest.functions, fn)) return manifest.functions[fn];
  const handler = vars.PSKIT_HANDLER;
  if (handler) return { name: fn || handler, handler, routes: [], timeout: null, memory: null, resourceName: null };
  const names = Object.keys(manifest.functions);
  if (names.length === 1 && !fn) return manifest.functions[names[0]];
  const known = names.sort().join(", ") || "<none>";
  throw new LookupError(
    `Cannot resolve function ${JSON.stringify(fn)}. Set PSKIT_FUNCTION/PSKIT_HANDLER or check ` +
      `${MANIFEST_FILE}. Known functions: ${known}`,
  );
}

module.exports = { MANIFEST_FILE, bundleRoot, fromDict, loadManifest, setManifest, registerManifest, resolveFunction };
