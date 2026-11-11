"use strict";
// Console routes under /ui: the page and its files, the session, sign-in and sign-out, and the signed-in API.

const { own, pget, pyStr } = require("../py");
const { S3Error, invalid } = require("../errors");
const { AUTH, UI_ON } = require("../config");
const { UTF8_STRICT, log } = require("../util");
const { safeEqual } = require("../checksums");
const { Auth } = require("../sigv4");
const { Response, jsonResponse } = require("../http");
const { UI_OPS, uiDownload, uiUpload } = require("./api");
const { login, logout, sessionInfo, sessionOf } = require("./session");
const { asset, indexPage } = require("./static");

const UI_READS = new Set(["ListBuckets", "ListObjects", "BucketInfo", "HeadObject", "ListVersions", "ListUploads", "Presign", "Stats"]);

/** Every /ui request: the page and its files, the session calls, downloads, uploads and /ui/api/<Operation>. */
async function uiRoute(req) {
  if (!UI_ON) throw new S3Error("NotFound", "The web console is off (S3_UI=off).", 404);
  const p = req.raw_path;
  const read = req.method === "GET" || req.method === "HEAD";
  if (p === "/ui") return new Response(302, Buffer.alloc(0), { Location: "/ui/" }, "text/plain");
  if (p === "/ui/" && read) return indexPage();
  if (p.startsWith("/ui/assets/") && read) return asset(p.slice("/ui/assets/".length));
  const found = sessionOf(req.headers.cookie || "");
  if (p === "/ui/session") return sessionInfo(found);
  if (p === "/ui/login" && req.method === "POST") return login(req);
  if (p === "/ui/logout" && req.method === "POST") return logout(found);
  if (AUTH !== "off" && !found) throw new S3Error("AccessDenied", "Sign in first.", 401);
  const user = found ? found.user : "";
  if (p === "/ui/download" && req.method === "GET") return uiDownload(req);
  if (AUTH !== "off" && !safeEqual(req.headers["x-s3-csrf"] || "", found ? found.csrf : "")) {
    throw new S3Error("AccessDenied", "The console's request token is missing; reload the page.", 403);
  }
  if (p === "/ui/upload" && req.method === "PUT") return uiUpload(req);
  if (p.startsWith("/ui/api/") && req.method === "POST") {
    let params;
    try {
      params = JSON.parse(UTF8_STRICT.decode(await req.smallBody()) || "{}");
    } catch {
      throw invalid("The request body is not valid JSON.");
    }
    const op = p.slice("/ui/api/".length);
    if (!own(UI_OPS, op)) throw new S3Error("NotImplemented", `Unknown console operation ${op}.`, 501);
    req.auth = new Auth(user || "console", "console");
    const result = await UI_OPS[op](params, req);
    if (!UI_READS.has(op)) log("console", op, pyStr(pget(params, "bucket", "")), pyStr(pget(params, "key", "")), "by", user || "console");
    return jsonResponse(result);
  }
  throw new S3Error("NotFound", "Not found.", 404);
}

module.exports = { uiRoute };
