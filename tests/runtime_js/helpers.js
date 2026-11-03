"use strict";
// Shared fixtures for the Node.js runtime tests (run with `node --test tests/runtime_js`).

const fs = require("fs");
const os = require("os");
const path = require("path");

const RUNTIME = path.resolve(__dirname, "..", "..", "src", "py_serverless_kit", "runtime_js");
process.env.PSKIT_LOG_LEVEL = process.env.PSKIT_LOG_LEVEL || "CRITICAL";

function runtime(name = "index") {
  return require(path.join(RUNTIME, name));
}

/** A temporary bundle root with the given files; sets PSKIT_BUNDLE_ROOT. */
function makeBundle(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pskit-js-"));
  for (const [rel, text] of Object.entries(files)) {
    const file = path.join(root, rel);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, text);
  }
  process.env.PSKIT_BUNDLE_ROOT = root;
  return root;
}

module.exports = { RUNTIME, runtime, makeBundle };
