"use strict";
// CORS: the bucket's rules, preflight matching and the headers added to responses.

const { g, own, pyStrip } = require("./py");
const { S3Error, invalid, malformed } = require("./errors");
const { parseXml, text } = require("./util");
const { configsOf } = require("./store");

/** Whether `value` matches `pattern` (* any run of characters, ? one character); "s3:" patterns ignore case. */
function wild(pattern, value) {
  const regex = `^${pattern.split("*").map((p) => p.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&").replace(/\\\?/g, ".")).join(".*")}$`;
  return new RegExp(regex, pattern.toLowerCase().startsWith("s3:") ? "iu" : "u").test(value);
}

function corsRules(bucket) {
  if (own(bucket.parsed, "cors")) return bucket.parsed.cors;
  let rules = [];
  const raw = g(configsOf(bucket), "cors");
  if (raw) {
    try {
      const root = parseXml(Buffer.from(raw, "utf8"));
      for (const rule of root.iter("CORSRule")) {
        const all = (tag) => rule.findall(tag).map((e) => pyStrip(e.text || ""));
        rules.push({
          origins: all("AllowedOrigin"),
          methods: all("AllowedMethod").map((m) => m.toUpperCase()),
          headers: all("AllowedHeader").map((h) => h.toLowerCase()),
          expose: all("ExposeHeader"),
          max_age: text(rule, "MaxAgeSeconds") ? [text(rule, "MaxAgeSeconds")] : [],
        });
      }
    } catch (err) {
      if (!(err instanceof S3Error)) throw err;
      rules = [];
    }
  }
  bucket.parsed.cors = rules;
  return rules;
}

function corsMatch(bucket, origin, method, reqHeaders) {
  for (const rule of corsRules(bucket)) {
    if (!rule.origins.some((o) => wild(o, origin))) continue;
    if (!rule.methods.includes(method)) continue;
    if (reqHeaders.some((h) => h && !rule.headers.some((a) => wild(a, h)))) continue;
    const anyOrigin = rule.origins.length === 1 && rule.origins[0] === "*";
    const out = {
      "Access-Control-Allow-Origin": anyOrigin ? "*" : origin,
      "Access-Control-Allow-Methods": rule.methods.join(", "),
      Vary: "Origin, Access-Control-Request-Headers, Access-Control-Request-Method",
    };
    if (origin !== "*" && !anyOrigin) out["Access-Control-Allow-Credentials"] = "true";
    if (rule.expose.length) out["Access-Control-Expose-Headers"] = rule.expose.join(", ");
    if (rule.max_age.length) out["Access-Control-Max-Age"] = rule.max_age[0];
    if (reqHeaders.length) out["Access-Control-Allow-Headers"] = reqHeaders.join(", ");
    return out;
  }
  return null;
}

function validateCors(body) {
  const root = parseXml(body);
  if (root.tag !== "CORSConfiguration") throw malformed();
  const rules = root.findall("CORSRule");
  if (!rules.length || rules.length > 100) throw malformed();
  for (const rule of rules) {
    const methods = rule.findall("AllowedMethod").map((e) => pyStrip(e.text || ""));
    if (!methods.length || !rule.findall("AllowedOrigin").length) throw malformed();
    for (const m of methods) {
      if (!["GET", "PUT", "POST", "DELETE", "HEAD"].includes(m)) {
        throw invalid(`Found unsupported HTTP method in CORS config. Unsupported method is ${m}`, "CORSRule/AllowedMethod", m);
      }
    }
  }
}

module.exports = { corsRules, corsMatch, validateCors };
