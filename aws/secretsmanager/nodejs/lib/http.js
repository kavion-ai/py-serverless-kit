"use strict";
// HTTP: the Secrets Manager API (POST / with X-Amz-Target), /health, and the console routes under /ui/.

const crypto = require("crypto");
const { AUTH, MAX_BODY, REGION, SESSION_TTL, UI_ON, UI_PASSWORD, VERSION } = require("./config");
const { ApiError } = require("./errors");
const { run } = require("./operations");
const { verifySigv4 } = require("./sigv4");
const { store } = require("./store");
const { log, safeEqual } = require("./util");
const ui = require("./console");

function send(res, status, body, ctype, extra = {}) {
  const data = Buffer.isBuffer(body) ? body : Buffer.from(body);
  res.writeHead(status, {
    "Content-Type": ctype,
    "Content-Length": data.length,
    "x-amzn-RequestId": crypto.randomUUID(),
    Server: `pskit-secretsmanager/${VERSION}`,
    ...extra,
  });
  res.end(res.req.method === "HEAD" ? undefined : data);
}

const sendJson = (res, status, data, extra) => send(res, status, JSON.stringify(data), "application/x-amz-json-1.1", extra);

function sendError(res, err, isUi = false) {
  sendJson(res, err.status, { __type: err.code, message: err.message }, isUi ? {} : { "x-amzn-ErrorType": err.code });
}

function params(body) {
  let data;
  try {
    data = body.toString("utf8").trim() ? JSON.parse(body.toString("utf8")) : {};
  } catch {
    throw new ApiError("SerializationException", "The request body is not valid JSON.");
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new ApiError("SerializationException", "The request body must be a JSON object.");
  return data;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(new ApiError("SerializationException", "The request body is too large.", 413));
        req.destroy();
      } else chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function headerMap(req) {
  // Node joins repeated headers with ", "; AWS's canonical form joins them with ",".
  const out = {};
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    const name = req.rawHeaders[i].toLowerCase();
    const value = req.rawHeaders[i + 1].trim();
    out[name] = out[name] === undefined ? value : `${out[name]},${value}`;
  }
  return out;
}

function handleGet(req, res, pathname) {
  if (pathname === "/health" || pathname === "/healthz") {
    return send(res, 200, JSON.stringify({ status: "ok", secrets: Object.keys(store.secrets).length, version: VERSION }), "application/json");
  }
  if (UI_ON && (pathname === "/" || pathname === "/ui")) return send(res, 302, "", "text/plain", { Location: "/ui/" });
  if (UI_ON && pathname === "/ui/") return send(res, 200, ui.uiHtml(), "text/html; charset=utf-8", ui.UI_HEADERS);
  if (UI_ON && pathname.startsWith("/ui/assets/")) {
    const found = ui.uiAsset(pathname.slice("/ui/assets/".length));
    if (!found) throw new ApiError("NotFound", "Not found.", 404);
    return send(res, 200, found[0], found[1], { "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff" });
  }
  if (UI_ON && pathname === "/ui/session") {
    const found = ui.sessionOf(req.headers.cookie);
    const data = AUTH === "off"
      ? { authenticated: true, user: "", auth: false, csrf: "" }
      : { authenticated: Boolean(found), user: found ? found.user : "", auth: true, csrf: found ? found.csrf : "", password_login: Boolean(UI_PASSWORD) };
    return send(res, 200, JSON.stringify(data), "application/json", { "Cache-Control": "no-store" });
  }
  return sendError(res, new ApiError("NotFound", "Not found. The Secrets Manager API takes POST / with X-Amz-Target.", 404));
}

function handleUi(req, res, pathname, body) {
  const ip = req.socket.remoteAddress || "";
  if (pathname === "/ui/login") {
    if (AUTH === "off") return sendJson(res, 200, { authenticated: true, csrf: "" });
    if (ui.throttled(ip)) throw new ApiError("ThrottlingException", "Too many failed sign-ins; wait 5 minutes.", 429);
    const data = params(body);
    const user = String(data.user || "");
    const password = String(data.password || "");
    if (!ui.checkLogin(user, password)) {
      ui.failed(ip);
      log("console sign-in refused from", ip);
      throw new ApiError("AccessDeniedException", "Wrong access key or password.", 401);
    }
    const [sid, csrf] = ui.newSession(user || "console");
    log("console sign-in", user || "console", "from", ip);
    return sendJson(res, 200, { authenticated: true, user, csrf }, {
      "Set-Cookie": `sm_session=${sid}; Path=/ui/; HttpOnly; SameSite=Strict; Max-Age=${SESSION_TTL}`,
      "Cache-Control": "no-store",
    });
  }
  const found = ui.sessionOf(req.headers.cookie);
  if (pathname === "/ui/logout") {
    if (found) ui.sessions.delete(found.id);
    return sendJson(res, 200, { authenticated: false }, { "Set-Cookie": "sm_session=; Path=/ui/; HttpOnly; Max-Age=0" });
  }
  if (!pathname.startsWith("/ui/api/")) throw new ApiError("NotFound", "Not found.", 404);
  if (AUTH !== "off") {
    if (!found) throw new ApiError("AccessDeniedException", "Sign in first.", 401);
    if (!safeEqual(req.headers["x-sm-csrf"] || "", found.csrf)) {
      throw new ApiError("AccessDeniedException", "The console's request token is missing; reload the page.", 403);
    }
  }
  const who = found ? `console:${found.user}` : "console";
  return sendJson(res, 200, run(pathname.slice("/ui/api/".length), params(body), REGION, who), { "Cache-Control": "no-store" });
}

async function handle(req, res) {
  const url = new URL(req.url, "http://localhost");
  const rawPath = req.url.split("?")[0];
  const query = req.url.includes("?") ? req.url.slice(req.url.indexOf("?") + 1) : "";
  try {
    if (req.method === "GET" || req.method === "HEAD") return handleGet(req, res, url.pathname);
    if (req.method !== "POST") throw new ApiError("NotFound", "Not found.", 404);
    const body = await readBody(req);
    if (url.pathname.startsWith("/ui/")) {
      if (!UI_ON) throw new ApiError("NotFound", "The web console is off (SM_UI=off).", 404);
      return handleUi(req, res, url.pathname, body);
    }
    const headers = headerMap(req);
    const target = headers["x-amz-target"] || "";
    const dot = target.indexOf(".");
    const service = dot < 0 ? target : target.slice(0, dot);
    const operation = dot < 0 ? "" : target.slice(dot + 1);
    if (service !== "secretsmanager" || !operation) throw new ApiError("UnknownOperationException", "X-Amz-Target must be secretsmanager.<Operation>.");
    let who = "anonymous";
    let region = REGION;
    if (AUTH !== "off") [who, region] = verifySigv4("POST", rawPath, query, headers, body);
    return sendJson(res, 200, run(operation, params(body), region, who));
  } catch (err) {
    if (err instanceof ApiError) return sendError(res, err, url.pathname.startsWith("/ui/"));
    log("error:", err && err.stack ? err.stack : String(err));
    return sendError(res, new ApiError("InternalServiceError", "The server failed to process the request.", 500));
  }
}

module.exports = { send, sendJson, sendError, params, readBody, headerMap, handleGet, handleUi, handle };
