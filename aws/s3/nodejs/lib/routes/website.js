"use strict";
// Static website hosting: /-/website/<bucket>/ and <bucket>.s3-website.<domain>.

const { g, pyInt } = require("../py");
const { notAllowed } = require("../errors");
const { esc, parseXml, quote, text } = require("../util");
const { configsOf, getStore } = require("../store");
const { allowed } = require("../access");
const { objectHeaders } = require("../versions");
const { Response } = require("../http");

function webError(status, code, message) {
  const title = { 403: "403 Forbidden", 404: "404 Not Found" }[status] || String(status);
  const body = `<html><head><title>${title}</title></head><body><h1>${title}</h1><ul><li>Code: ${esc(code)}</li>` +
    `<li>Message: ${esc(message)}</li></ul></body></html>`;
  return new Response(status, body, {}, "text/html; charset=utf-8");
}

function website(req, bucketName, key, base) {
  if (req.method !== "GET" && req.method !== "HEAD") throw notAllowed();
  const bucket = getStore().buckets.get(bucketName);
  if (!bucket) return webError(404, "NoSuchBucket", `The specified bucket does not exist: ${bucketName}`);
  const raw = g(configsOf(bucket), "website");
  if (!raw) return webError(404, "NoSuchWebsiteConfiguration", "The specified bucket does not have a website configuration");
  const root = parseXml(Buffer.from(raw, "utf8"));
  const redirectAll = root.find("RedirectAllRequestsTo");
  if (redirectAll) {
    const proto = text(redirectAll, "Protocol") || "http";
    return new Response(301, Buffer.alloc(0), { Location: `${proto}://${text(redirectAll, "HostName")}/${quote(key)}` });
  }
  const suffix = text(root, "IndexDocument/Suffix");
  const errorDoc = text(root, "ErrorDocument/Key");
  const rules = root.findall("RoutingRules/RoutingRule");
  const redirectFor = (code) => {
    for (const rule of rules) {
      const cond = rule.find("Condition");
      if (cond) {
        const pfx = text(cond, "KeyPrefixEquals");
        const err = text(cond, "HttpErrorCodeReturnedEquals");
        if (pfx && !key.startsWith(pfx)) continue;
        if (err && String(code) !== err) continue;
        if (!err && code !== null) continue;
      } else if (code !== null) {
        continue;
      }
      const red = rule.find("Redirect");
      let newKey = key;
      if (text(red, "ReplaceKeyWith")) newKey = text(red, "ReplaceKeyWith");
      else if (red && red.find("ReplaceKeyPrefixWith") && cond) newKey = text(red, "ReplaceKeyPrefixWith") + key.slice(text(cond, "KeyPrefixEquals").length);
      const host = text(red, "HostName") || req.host;
      const proto = text(red, "Protocol") || "http";
      const status = pyInt(text(red, "HttpRedirectCode") || "301");
      return new Response(status, Buffer.alloc(0), { Location: `${proto}://${host}${!text(red, "HostName") ? base : "/"}${quote(newKey)}` });
    }
    return null;
  };
  const early = redirectFor(null);
  if (early) return early;
  const target = !key || key.endsWith("/") ? key + suffix : key;
  const fetch = (name) => {
    const rec = bucket.objects.get(name);
    if (!rec || rec.versions[0].dm) return null;
    return rec.versions[0];
  };
  const version = fetch(target);
  if (!version && key && !key.endsWith("/") && fetch(`${key}/${suffix}`)) {
    return new Response(302, Buffer.alloc(0), { Location: `${base}${quote(key)}/` });
  }
  // Website requests are never signed: the policy and ACLs decide, as for any anonymous request.
  if (version && !allowed(req, bucket, "s3:GetObject", target, version)) return webError(403, "AccessDenied", "Access Denied");
  if (!version) {
    const red = redirectFor(404);
    if (red) return red;
    const errVersion = errorDoc ? fetch(errorDoc) : null;
    if (errVersion && allowed(req, bucket, "s3:GetObject", errorDoc, errVersion)) {
      const type = errVersion.type || "text/html";
      return new Response(404, Buffer.alloc(0), { "Content-Type": type }, type, bucket.blobPath(errVersion.blob), 0, pyInt(errVersion.size));
    }
    return webError(404, "NoSuchKey", `The specified key does not exist. Key: ${target}`);
  }
  if (version.redirect) return new Response(301, Buffer.alloc(0), { Location: version.redirect });
  const headers = objectHeaders(version);
  return new Response(200, Buffer.alloc(0), headers, headers["Content-Type"], bucket.blobPath(version.blob), 0, pyInt(version.size));
}

module.exports = { website };
