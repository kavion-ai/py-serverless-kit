"use strict";
// Shared fixture for the Alibaba / Tencent / Huawei / Oracle / IBM / DigitalOcean adapter tests.
const fs = require("fs");
const os = require("os");
const path = require("path");

const RT = path.join(__dirname, "..", "..", "src", "py_serverless_kit", "runtime_js");

const HANDLERS = `
exports.api = (event) => ({ method: event.http.method, path: event.http.path, q: event.http.query.q || null, body: event.http.text(), id: event.http.pathParams.id || null });
exports.task = (event) => { if (event.data && event.data.fail) throw new TypeError("nope"); return { got: event.data, type: event.type }; };
exports.batch = (event) => { globalThis.__seen = { type: event.type, source: event.source, records: event.records.map((r) => ({ bucket: r.bucket, key: r.key, action: r.action, body: r.text() })) }; return { n: event.records.length }; };
`;

const FUNCTIONS = {
  api: { handler: "handlers.api", routes: [{ method: "ANY", path: "/items/{id}" }, { method: "ANY", path: "/" }] },
  task: { handler: "handlers.task", routes: [] },
  batch: { handler: "handlers.batch", routes: [] },
};

function bundle(provider, fn) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), `pskit-${provider}-`));
  fs.writeFileSync(path.join(root, "handlers.js"), HANDLERS);
  fs.writeFileSync(
    path.join(root, "pskit_manifest.json"),
    JSON.stringify({ service: "svc", stage: "dev", provider, functions: FUNCTIONS }),
  );
  process.env.PSKIT_BUNDLE_ROOT = root;
  process.env.PSKIT_FUNCTION = fn;
  require(path.join(RT, "manifest")).setManifest(null);
  require(path.join(RT, "dispatch")).clearHandlerCache();
  globalThis.__seen = undefined;
  return require(path.join(RT, "adapters", provider));
}

const envelope = (kind, data, extra = {}) => Object.assign({ __pskit: kind, data }, extra);

module.exports = { RT, bundle, envelope };
