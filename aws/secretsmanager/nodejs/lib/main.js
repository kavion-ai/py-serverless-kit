"use strict";
// main(): load the store, migrate it to the current encryption settings, then serve (or --check / --rewrap).

const http = require("http");
const { AUTH, BIND, CREDENTIALS, PORT, STORE_FILE, UI_ON, VERSION, env } = require("./config");
const { setServerDir } = require("./console");
const { handle } = require("./http");
const { Keyring } = require("./keyring");
const { store } = require("./store");
const { log } = require("./util");

function check() {
  const host = BIND === "0.0.0.0" || !BIND ? "127.0.0.1" : BIND;
  const req = http.get({ host, port: PORT, path: "/health", timeout: 3000 }, (res) => process.exit(res.statusCode === 200 ? 0 : 1));
  req.on("timeout", () => process.exit(1));
  req.on("error", () => process.exit(1));
}

/** `serverDir` is the directory of server.js; the console files are found from there. */
function main(serverDir) {
  if (serverDir) setServerDir(serverDir);
  if (process.argv.includes("--check")) return check();
  if (AUTH !== "sigv4" && AUTH !== "off") {
    console.error("SM_AUTH must be sigv4 or off");
    process.exit(2);
  }
  const rewrapOnly = process.argv.includes("--rewrap");
  if (AUTH !== "off" && !Object.keys(CREDENTIALS).length && !rewrapOnly) {
    console.error("set SM_SECRET_ACCESS_KEY (and SM_ACCESS_KEY_ID), or SM_CREDENTIALS=id:secret, or SM_AUTH=off");
    process.exit(2);
  }
  try {
    store.load(new Keyring(env));
  } catch (err) {
    console.error(`secretsmanager: ${err.message}`);
    process.exit(2);
  }
  // Encrypt a plain file, decrypt it with SM_ENCRYPTION=off, or rewrap the data keys to the current master key.
  if (store.stale()) store.save();
  const keyring = store.keyring;
  if (rewrapOnly) {
    log(keyring.alg ? `rewrapped ${STORE_FILE} to master key '${keyring.current}'` : `wrote ${STORE_FILE} unencrypted`);
    return;
  }
  const server = http.createServer((req, res) => {
    handle(req, res);
  });
  server.listen(PORT, BIND, () => {
    log(`Secrets Manager compatible server ${VERSION} (Node.js) on ${BIND}:${PORT}, data ${STORE_FILE}, ${Object.keys(store.secrets).length} secrets, auth ${AUTH}${UI_ON ? ", console /ui/" : ""}${keyring.alg ? `, encryption ${keyring.alg} (master key '${keyring.current}')` : ", not encrypted"}`);
    if (AUTH === "off") log("warning: SM_AUTH=off, anyone who reaches the port can read every secret");
    if (!keyring.alg) log("warning: secrets are stored unencrypted; set SM_MASTER_KEY (openssl rand -base64 32) to encrypt them");
  });
  const stop = () => server.close(() => process.exit(0));
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}

module.exports = { main, check };
