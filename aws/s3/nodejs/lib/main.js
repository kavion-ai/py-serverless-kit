"use strict";
// main(): start the server (or `--check` its health), after checking the settings.

const http = require("http");

const { AUTH, BIND, CREDENTIALS, DATA_DIR, PORT, UI_ON, VERSION } = require("./config");
const { log } = require("./util");
const { Store, getStore, setStore } = require("./store");
const { lifecycleLoop } = require("./lifecycle");
const { dispatch } = require("./http");
const { route } = require("./routes/index");

function check() {
  const host = BIND === "0.0.0.0" || !BIND ? "127.0.0.1" : BIND;
  const req = http.get({ host, port: PORT, path: "/-/health", timeout: 3000 }, (res) => process.exit(res.statusCode === 200 ? 0 : 1));
  req.on("timeout", () => process.exit(1));
  req.on("error", () => process.exit(1));
}

function main() {
  if (process.argv.slice(2).includes("--check")) return check();
  if (AUTH !== "sigv4" && AUTH !== "off") {
    console.error("S3_AUTH must be sigv4 or off");
    process.exit(2);
  }
  if (AUTH !== "off" && !CREDENTIALS.size) {
    console.error("set S3_SECRET_ACCESS_KEY (and S3_ACCESS_KEY_ID), or S3_CREDENTIALS=id:secret, or S3_AUTH=off");
    process.exit(2);
  }
  setStore(new Store(DATA_DIR));
  const server = http.createServer({ maxHeaderSize: 65536, requestTimeout: 0 }, (nreq, res) => {
    // A client that goes away mid-request is not an error worth a stack trace.
    nreq.on("error", () => {});
    res.on("error", () => {});
    dispatch(nreq, res, route).catch((err) => {
      log("error:", err && err.stack ? err.stack : String(err));
      res.destroy();
    });
  });
  server.on("clientError", (err, socket) => {
    if (err.code === "ECONNRESET" || !socket.writable) {
      socket.destroy();
      return;
    }
    socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
  });
  server.listen(PORT, BIND, () => {
    lifecycleLoop();
    log(`S3 compatible server ${VERSION} (Node.js) on ${BIND}:${PORT}, data ${DATA_DIR}, ${getStore().buckets.size} buckets, ` +
      `auth ${AUTH}${UI_ON ? ", console /ui/" : ""}`);
    if (AUTH === "off") log("warning: S3_AUTH=off, anyone who reaches the port can read and change every object");
  });
  process.on("SIGTERM", () => process.exit(0));
  process.on("SIGINT", () => process.exit(0));
  return undefined;
}
module.exports = { main };
