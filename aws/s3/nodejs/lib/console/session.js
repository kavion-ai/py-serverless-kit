"use strict";
// Console sessions: sign-in (with throttling), the HttpOnly session cookie, the CSRF token and sign-out.
// The sessions live only in this module; other modules use the functions below.

const crypto = require("crypto");

const { pget, pyStr, pyStrip } = require("../py");
const { S3Error, invalid } = require("../errors");
const { AUTH, CREDENTIALS, REGION, SESSION_TTL, UI_PASSWORD, VERSION } = require("../config");
const { UTF8_STRICT, epoch, log } = require("../util");
const { safeEqual } = require("../checksums");
const { Response, jsonResponse } = require("../http");

const SESSIONS = new Map(); // session id -> {user, csrf, expires}
const FAILURES = new Map(); // client address -> times of failed sign-ins

function checkLogin(user, password) {
  if (UI_PASSWORD) return safeEqual(password, UI_PASSWORD);
  const secret = CREDENTIALS.get(user);
  // Compare against a dummy for an unknown user, so the time is the same.
  return safeEqual(password, secret === undefined ? "\0".repeat(32) : secret) && secret !== undefined;
}

/** Ten failed sign-ins from one address in five minutes lock it out. */
function throttled(ip) {
  const t = epoch();
  const recent = (FAILURES.get(ip) || []).filter((f) => t - f < 300);
  FAILURES.set(ip, recent);
  return recent.length >= 10;
}

function failed(ip) {
  if (!FAILURES.has(ip)) FAILURES.set(ip, []);
  FAILURES.get(ip).push(epoch());
}

/** [session id, CSRF token] of a new session (expired ones are dropped). */
function newSession(user) {
  const sid = crypto.randomBytes(32).toString("base64url");
  const csrf = crypto.randomBytes(24).toString("base64url");
  const t = epoch();
  for (const [key, s] of SESSIONS) if (s.expires < t) SESSIONS.delete(key);
  SESSIONS.set(sid, { user, csrf, expires: t + SESSION_TTL });
  return [sid, csrf];
}

/** The live session the Cookie header names ({user, csrf, expires, id}), or null. */
function sessionOf(cookieHeader) {
  for (const part of cookieHeader.split(";")) {
    const item = pyStrip(part);
    const at = item.indexOf("=");
    const name = at < 0 ? item : item.slice(0, at);
    const value = at < 0 ? "" : item.slice(at + 1);
    if (name === "s3_session") {
      const found = SESSIONS.get(value);
      if (found && found.expires > epoch()) return { ...found, id: value };
    }
  }
  return null;
}

/** GET /ui/session: who is signed in, and the CSRF token the page sends back. */
function sessionInfo(found) {
  let data;
  if (AUTH === "off") {
    data = { authenticated: true, user: "", auth: false, csrf: "" };
  } else {
    data = {
      authenticated: Boolean(found),
      user: found ? found.user : "",
      auth: true,
      csrf: found ? found.csrf : "",
      password_login: Boolean(UI_PASSWORD),
    };
  }
  Object.assign(data, { region: REGION, version: VERSION });
  return jsonResponse(data);
}

/** POST /ui/login {user, password}: sets the session cookie and returns the CSRF token. */
async function login(req) {
  const ip = req.ip;
  const body = await req.smallBody(65536);
  if (AUTH === "off") return jsonResponse({ authenticated: true, csrf: "" }, {});
  if (throttled(ip)) throw new S3Error("SlowDown", "Too many failed sign-ins; wait 5 minutes.", 429);
  let data;
  try {
    data = JSON.parse(UTF8_STRICT.decode(body) || "{}");
  } catch {
    throw invalid("The request body is not valid JSON.");
  }
  const user = pyStr(pget(data, "user") || "");
  const password = pyStr(pget(data, "password") || "");
  if (!checkLogin(user, password)) {
    failed(ip);
    log("console sign-in refused from", ip);
    throw new S3Error("AccessDenied", "Wrong access key or password.", 401);
  }
  const [sid, csrf] = newSession(user || "console");
  log("console sign-in", user || "console", "from", ip);
  return jsonResponse({ authenticated: true, user, csrf }, {
    "Set-Cookie": `s3_session=${sid}; Path=/ui/; HttpOnly; SameSite=Strict; Max-Age=${SESSION_TTL}`,
    "Cache-Control": "no-store",
  });
}

/** POST /ui/logout: ends the session and clears the cookie. */
function logout(found) {
  if (found) SESSIONS.delete(found.id);
  return new Response(200, '{"authenticated": false}', { "Set-Cookie": "s3_session=; Path=/ui/; HttpOnly; Max-Age=0" }, "application/json");
}

module.exports = { sessionOf, sessionInfo, login, logout };
