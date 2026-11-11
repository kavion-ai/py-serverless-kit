"use strict";
// The routing entry: health, console, website, virtual-hosted / path-style addressing, CORS preflight, browser
// POST, authentication, then the service, bucket or object routes.

const { pyDumps, pyStrip } = require("../py");
const { S3Error, denied, noBucket, notAllowed } = require("../errors");
const { ACCOUNT, DOMAINS, UI_ON, VERSION } = require("../config");
const { unquote } = require("../util");
const { getStore } = require("../store");
const { authenticate } = require("../access");
const { corsMatch, corsRules } = require("../cors");
const { Response } = require("../http");
const { listBuckets } = require("./service");
const { bucketRoute } = require("./bucket");
const { objectRoute } = require("./objects");
const { postObject } = require("./post");
const { website } = require("./website");
const { uiRoute } = require("../console/router");

function bucketFromHost(host) {
  const name = host.startsWith("[") ? "" : host.replace(/:[^:]*$/, "").toLowerCase();
  for (const domain of DOMAINS) if (name.endsWith(`.${domain}`)) return name.slice(0, -domain.length - 1);
  const match = /^(.+)\.s3[.-](?:[a-z0-9-]+\.)?amazonaws\.com$/.exec(name);
  return match ? match[1] : "";
}

async function route(req) {
  if (["/-/health", "/-/healthz"].includes(req.raw_path) ||
    (["/health", "/healthz"].includes(req.raw_path) && req.headers.authorization === undefined && !Object.keys(req.q).length)) {
    return new Response(200, pyDumps({ status: "ok", buckets: getStore().buckets.size, version: VERSION }), {}, "application/json");
  }
  if (req.raw_path === "/ui" || req.raw_path.startsWith("/ui/")) return uiRoute(req);
  if (req.raw_path.startsWith("/-/website/")) {
    const rest = req.raw_path.slice("/-/website/".length);
    const slash = rest.indexOf("/");
    const bucket = slash < 0 ? rest : rest.slice(0, slash);
    const key = slash < 0 ? "" : rest.slice(slash + 1);
    return website(req, unquote(bucket), unquote(key), `/-/website/${bucket}/`);
  }
  const hostBucket = bucketFromHost(req.host);
  const web = /^(.+)\.s3-website[.-]/.exec(req.host.toLowerCase());
  if (web) return website(req, web[1], unquote(req.raw_path.replace(/^\/+/, "")), "/");
  if (hostBucket) {
    req.vhost = hostBucket;
    req.bucket = hostBucket;
    req.key = unquote(req.raw_path.slice(1));
  } else {
    const rest = req.raw_path.slice(1);
    const slash = rest.indexOf("/");
    req.bucket = unquote(slash < 0 ? rest : rest.slice(0, slash));
    req.key = unquote(slash < 0 ? "" : rest.slice(slash + 1));
  }
  if (req.raw_path === "/" && !hostBucket && UI_ON && req.method === "GET" && req.headers.authorization === undefined &&
    req.q["X-Amz-Signature"] === undefined && (req.headers.accept || "").includes("text/html")) {
    return new Response(302, Buffer.alloc(0), { Location: "/ui/" }, "text/plain");
  }
  if (req.method === "OPTIONS") return preflight(req);
  if (req.method === "POST" && req.bucket && !req.key && (req.headers["content-type"] || "").startsWith("multipart/form-data") &&
    req.headers.authorization === undefined) {
    return postObject(req);
  }
  authenticate(req);
  const expectedOwner = req.headers["x-amz-expected-bucket-owner"];
  if (expectedOwner && expectedOwner !== ACCOUNT) throw denied();
  if (!req.bucket) {
    if (req.method === "GET") return listBuckets(req);
    throw notAllowed();
  }
  if (Buffer.byteLength(req.key, "utf8") > 1024) throw new S3Error("KeyTooLongError", "Your key is too long", 400);
  if (!req.key) return bucketRoute(req);
  return objectRoute(req);
}

function preflight(req) {
  const origin = req.headers.origin || "";
  const method = req.headers["access-control-request-method"] || "";
  if (!origin || !method) throw new S3Error("BadRequest", "Insufficient information. Origin request header needed.", 400);
  const bucket = getStore().buckets.get(req.bucket);
  if (!bucket) throw noBucket(req.bucket);
  if (!corsRules(bucket).length) throw new S3Error("CORSResponse", "CORS is not enabled for this bucket.", 403);
  const wanted = (req.headers["access-control-request-headers"] || "").split(",").filter((h) => pyStrip(h)).map((h) => pyStrip(h).toLowerCase());
  const found = corsMatch(bucket, origin, method.toUpperCase(), wanted);
  if (!found) {
    throw new S3Error("CORSResponse", "This CORS request is not allowed. This is usually because the evalution of " +
      "Origin, request method / Access-Control-Request-Method or Access-Control-Request-Headers are " +
      "not whitelisted by the resource's CORS spec.", 403);
  }
  return new Response(200, Buffer.alloc(0), found);
}

module.exports = { route };
