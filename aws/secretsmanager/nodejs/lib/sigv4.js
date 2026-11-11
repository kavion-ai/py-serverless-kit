"use strict";
// AWS Signature Version 4: checks a request's Authorization header exactly as AWS does.

const crypto = require("crypto");
const { AUTH_RE, CREDENTIALS, SKEW } = require("./config");
const { ApiError } = require("./errors");
const { byCodePoint, hmac, sha256, safeEqual } = require("./util");

/** RFC 3986 encoding, as Python's urllib.parse.quote(safe="-_.~"). */
function uriEncode(text) {
  return encodeURIComponent(text).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

function parseQuery(query) {
  const pairs = [];
  for (const part of query.split(/[&;]/)) {
    if (!part) continue;
    const at = part.indexOf("=");
    const raw = (s) => decodeURIComponent(s.replace(/\+/g, " "));
    pairs.push(at < 0 ? [raw(part), ""] : [raw(part.slice(0, at)), raw(part.slice(at + 1))]);
  }
  return pairs;
}

/** [access key id, region] of a correctly signed request, else an ApiError as AWS answers it. */
function verifySigv4(method, pathname, query, headers, body) {
  const auth = headers.authorization || "";
  if (!auth) throw new ApiError("MissingAuthenticationTokenException", "Missing Authentication Token");
  const match = AUTH_RE.exec(auth.trim());
  if (!match) {
    throw new ApiError("IncompleteSignatureException", "Authorization header requires Credential, SignedHeaders and Signature (AWS4-HMAC-SHA256).");
  }
  const [, credential, signedHeaders, signature] = match;
  const parts = credential.split("/");
  if (parts.length !== 5 || parts[4] !== "aws4_request") throw new ApiError("IncompleteSignatureException", "The Credential is not valid.");
  const [accessKey, day, region, service] = parts;
  if (!Object.prototype.hasOwnProperty.call(CREDENTIALS, accessKey)) {
    throw new ApiError("UnrecognizedClientException", "The security token included in the request is invalid.");
  }
  const secret = CREDENTIALS[accessKey];
  const amzDate = headers["x-amz-date"] || "";
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(amzDate);
  if (!m) throw new ApiError("IncompleteSignatureException", "X-Amz-Date is missing or not valid.");
  const when = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) / 1000;
  if (Math.abs(Date.now() / 1000 - when) > SKEW) {
    throw new ApiError("InvalidSignatureException", `Signature expired: ${amzDate} is now earlier or later than 15 minutes from the server's time.`);
  }
  if (day !== amzDate.slice(0, 8) || service !== "secretsmanager") {
    throw new ApiError("InvalidSignatureException", "The credential scope does not match the request.");
  }
  const names = signedHeaders.split(";");
  if (!names.includes("host") || names.some((n) => headers[n] === undefined)) {
    throw new ApiError("InvalidSignatureException", "SignedHeaders must include host and only headers that were sent.");
  }
  const payloadHash = sha256(body);
  const claimed = headers["x-amz-content-sha256"];
  if (claimed && claimed !== payloadHash) throw new ApiError("InvalidSignatureException", "x-amz-content-sha256 does not match the request body.");
  const pairs = parseQuery(query).map(([k, v]) => [uriEncode(k), uriEncode(v)]);
  pairs.sort((a, b) => byCodePoint(a[0], b[0]) || byCodePoint(a[1], b[1]));
  const canonical = [
    method.toUpperCase(),
    pathname || "/",
    pairs.map(([k, v]) => `${k}=${v}`).join("&"),
    names.map((n) => `${n}:${String(headers[n]).trim().split(/\s+/).join(" ")}\n`).join(""),
    signedHeaders,
    payloadHash,
  ].join("\n");
  const scope = `${day}/${region}/${service}/aws4_request`;
  const toSign = ["AWS4-HMAC-SHA256", amzDate, scope, sha256(canonical)].join("\n");
  let key = Buffer.from(`AWS4${secret}`, "utf8");
  for (const part of [day, region, service, "aws4_request"]) key = hmac(key, part);
  const expected = crypto.createHmac("sha256", key).update(toSign, "utf8").digest("hex");
  if (!safeEqual(expected, signature)) {
    throw new ApiError("InvalidSignatureException", "The request signature we calculated does not match the signature you provided. Check your AWS Secret Access Key and signing method.");
  }
  return [accessKey, region];
}

module.exports = { uriEncode, parseQuery, verifySigv4 };
