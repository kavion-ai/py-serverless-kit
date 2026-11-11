"use strict";
// Signatures: SigV4 / SigV2 verification (headers and presigned URLs), presign(), and request bodies: aws-chunked
// streaming with chunk and trailer signatures, Content-MD5, x-amz-content-sha256 and checksums.

const crypto = require("crypto");
const fs = require("fs");

const { asciiStrip, cmpStr, pyInt, pySplit, pyStrip } = require("./py");
const { S3Error, invalid } = require("./errors");
const { ALGORITHMS, CREDENTIALS, REGION, SKEW } = require("./config");
const { amzStamp, epoch, iso, parseTime, quote, splitQuery, unquote } = require("./util");
const { b64decodeStrict, checksumHeader, hmacSha256, newChecksum, safeEqual, sha256Hex } = require("./checksums");
const { getStore, unlink } = require("./store");

const AUTH4_RE = /^AWS4-HMAC-SHA256\s+Credential=([^,\s]+),\s*SignedHeaders=([^,\s]+),\s*Signature=([0-9a-f]{64})$/;

const V2_SUBRESOURCES = new Set(["acl", "cors", "delete", "lifecycle", "location", "logging", "notification",
  "partNumber", "policy", "requestPayment", "restore", "tagging", "torrent", "uploadId", "uploads", "versionId",
  "versioning", "versions", "website", "response-cache-control", "response-content-disposition",
  "response-content-encoding", "response-content-language", "response-content-type", "response-expires", "retention",
  "legal-hold", "object-lock", "encryption", "accelerate", "publicAccessBlock", "ownershipControls", "replication",
  "attributes", "policyStatus"]);

/** Who sent a request: principal is the access key id (null when anonymous); mode sigv4, sigv2, off, console or anonymous. */
class Auth {
  constructor(principal, mode = "anonymous") {
    this.principal = principal;
    this.mode = mode;
    this.via = ""; // s3:authType of a signed request: REST-HEADER, REST-QUERY-STRING or POST
    this.payload = ""; // x-amz-content-sha256 as signed
    this.key = Buffer.alloc(0); // the signing key, for streaming chunk signatures
    this.signature = "";
    this.amzDate = "";
    this.scope = "";
  }
}

function chunkSignature(auth, prev, kind, dataHash) {
  const empty = sha256Hex(Buffer.alloc(0));
  const toSign = kind === "trailer"
    ? ["AWS4-HMAC-SHA256-TRAILER", auth.amzDate, auth.scope, prev, dataHash].join("\n")
    : ["AWS4-HMAC-SHA256-PAYLOAD", auth.amzDate, auth.scope, prev, empty, dataHash].join("\n");
  return crypto.createHmac("sha256", auth.key).update(toSign, "utf8").digest("hex");
}

/** The decoded payload: plain, or aws-chunked with chunk signatures and trailing checksums. */
async function* payloadChunks(raw, headers, auth, trailers) {
  const mode = auth.payload || headers["x-amz-content-sha256"] || "";
  if (!mode.startsWith("STREAMING-")) {
    yield* raw.chunks();
    return;
  }
  if (!["STREAMING-AWS4-HMAC-SHA256-PAYLOAD", "STREAMING-AWS4-HMAC-SHA256-PAYLOAD-TRAILER",
    "STREAMING-UNSIGNED-PAYLOAD-TRAILER"].includes(mode)) {
    throw new S3Error("NotImplemented", `x-amz-content-sha256 ${mode} is not supported.`, 501);
  }
  const signed = mode.startsWith("STREAMING-AWS4-HMAC") && auth.key.length > 0;
  let prev = auth.signature;
  for (;;) {
    const line = asciiStrip((await raw.readline(4096)).toString("latin1"));
    if (!line) throw new S3Error("IncompleteBody", "The aws-chunked body ended early.");
    const semi = line.indexOf(";");
    const sizeText = semi < 0 ? line : line.slice(0, semi);
    const ext = semi < 0 ? "" : line.slice(semi + 1);
    let size;
    try {
      size = pyInt(sizeText, 16);
    } catch {
      throw new S3Error("InvalidRequest", "The aws-chunked body is not valid.");
    }
    const data = size > 0 ? await raw.read(size) : Buffer.alloc(0);
    if (data.length !== size) throw new S3Error("IncompleteBody", "The aws-chunked body ended early.");
    if (signed) {
      const at = ext.indexOf("chunk-signature=");
      const claimed = at < 0 ? "" : pyStrip(ext.slice(at + "chunk-signature=".length));
      const expected = chunkSignature(auth, prev, "chunk", sha256Hex(data));
      if (!safeEqual(claimed, expected)) throw new S3Error("SignatureDoesNotMatch", "The chunk signature does not match.", 403);
      prev = expected;
    }
    if (size) {
      await raw.read(2);
      yield data;
      continue;
    }
    const lines = [];
    for (;;) {
      const tl = (await raw.readline(8192)).toString("latin1");
      if (tl === "\r\n" || tl === "\n" || tl === "") break;
      lines.push(tl.replace(/[\r\n]+$/, ""));
    }
    let canonical = "";
    for (const tlText of lines) {
      const colon = tlText.indexOf(":");
      const name = pyStrip(colon < 0 ? tlText : tlText.slice(0, colon)).toLowerCase();
      const value = pyStrip(colon < 0 ? "" : tlText.slice(colon + 1));
      if (name === "x-amz-trailer-signature") {
        if (signed) {
          const expected = chunkSignature(auth, prev, "trailer", sha256Hex(Buffer.from(canonical, "utf8")));
          if (!safeEqual(value, expected)) throw new S3Error("SignatureDoesNotMatch", "The trailer signature does not match.", 403);
        }
      } else {
        trailers[name] = value;
        canonical += `${name}:${value}\n`;
      }
    }
    await raw.drain();
    return;
  }
}

class Received {
  constructor() {
    this.path = null;
    this.size = 0;
    this.md5 = "";
    this.checksum = null; // [alg, base64]
  }
}

/** [algorithm, value the client sent or "" for a trailer / to compute] of a write. */
function wantedChecksum(headers) {
  for (const alg of ALGORITHMS) {
    const value = headers[checksumHeader(alg)];
    if (value) return [alg, value];
  }
  const trailer = pyStrip(headers["x-amz-trailer"] || "").toLowerCase();
  for (const alg of ALGORITHMS) if (trailer === checksumHeader(alg)) return [alg, ""];
  const alg = (headers["x-amz-sdk-checksum-algorithm"] || headers["x-amz-checksum-algorithm"] || "").toUpperCase();
  if (alg) {
    if (!ALGORITHMS.includes(alg)) throw invalid(`Checksum algorithm ${alg} is not supported.`, "x-amz-checksum-algorithm", alg);
    return [alg, ""];
  }
  return ["", ""];
}

/** Read the payload into a temporary file (or memory), checking its length, MD5, SHA-256 and checksum. */
async function receive(raw, headers, auth, limit, alg = "", expected = "", toFile = true) {
  const out = new Received();
  const md5 = crypto.createHash("md5");
  const claimed = auth.payload || headers["x-amz-content-sha256"] || "";
  const sha = /^[0-9a-f]{64}$/.test(claimed) ? crypto.createHash("sha256") : null;
  const hasher = alg ? newChecksum(alg) : null;
  const trailers = {};
  const buf = [];
  let handle = null;
  try {
    if (toFile) {
      out.path = getStore().tempFile();
      handle = await fs.promises.open(out.path, "w");
    }
    for await (const data of payloadChunks(raw, headers, auth, trailers)) {
      out.size += data.length;
      if (out.size > limit) {
        throw new S3Error("EntityTooLarge", "Your proposed upload exceeds the maximum allowed size", 400, {
          MaxSizeAllowed: String(limit),
        });
      }
      md5.update(data);
      if (sha) sha.update(data);
      if (hasher) hasher.update(data);
      if (handle) await handle.write(data);
      else buf.push(data);
    }
  } catch (err) {
    if (handle) await handle.close().catch(() => {});
    if (out.path) unlink(out.path);
    throw err;
  }
  if (handle) await handle.close();
  try {
    const decoded = headers["x-amz-decoded-content-length"];
    if (decoded && claimed.startsWith("STREAMING-") && pyInt(decoded) !== out.size) {
      throw new S3Error("IncompleteBody", "The decoded body is not x-amz-decoded-content-length bytes long.");
    }
    const md5Digest = md5.digest();
    if (sha) {
      const computed = sha.digest("hex");
      if (computed !== claimed) {
        throw new S3Error("XAmzContentSHA256Mismatch", "The provided 'x-amz-content-sha256' header does not match what was computed.", 400, {
          ClientComputedContentSHA256: claimed,
          S3ComputedContentSHA256: computed,
        });
      }
    }
    out.md5 = md5Digest.toString("hex");
    const contentMd5 = headers["content-md5"];
    if (contentMd5) {
      let given;
      try {
        given = b64decodeStrict(contentMd5);
      } catch {
        throw new S3Error("InvalidDigest", "The Content-MD5 you specified was invalid.");
      }
      if (given.length !== 16) throw new S3Error("InvalidDigest", "The Content-MD5 you specified was invalid.");
      if (!given.equals(md5Digest)) throw new S3Error("BadDigest", "The Content-MD5 you specified did not match what we received.");
    }
    if (hasher) {
      const value = hasher.digest().toString("base64");
      const sent = expected || trailers[checksumHeader(alg)] || "";
      if (sent && sent !== value) throw new S3Error("BadDigest", `The ${alg} you specified did not match the calculated checksum.`);
      out.checksum = [alg, value];
    }
  } catch (err) {
    if (out.path) unlink(out.path);
    throw err;
  }
  return [out, Buffer.concat(buf)];
}

const uriEncode = (value, safe = "-_.~") => quote(value, safe);

function signingKey(secret, day, region, service) {
  let key = Buffer.from(`AWS4${secret}`, "utf8");
  for (const part of [day, region, service, "aws4_request"]) key = hmacSha256(key, part);
  return key;
}

function canonicalQuery(pairs, skip = "") {
  const enc = pairs.filter(([k]) => k !== skip).map(([k, v]) => [uriEncode(k), uriEncode(v)]);
  enc.sort((a, b) => cmpStr(a[0], b[0]) || cmpStr(a[1], b[1]));
  return enc.map(([k, v]) => `${k}=${v}`).join("&");
}

function canonicalPaths(rawPath) {
  const normalized = uriEncode(unquote(rawPath), "/-_.~");
  return normalized === rawPath ? [rawPath] : [rawPath, normalized];
}

const skewed = (extra = {}) =>
  new S3Error("RequestTimeTooSkewed", "The difference between the request time and the current time is too large.", 403, extra);

function verifyV4(method, rawPath, pairs, headers, presigned) {
  const q = Object.fromEntries(pairs);
  let credential;
  let signedHeaders;
  let signature;
  let amzDate;
  if (presigned) {
    if (q["X-Amz-Algorithm"] !== "AWS4-HMAC-SHA256") {
      throw new S3Error("AuthorizationQueryParametersError", 'X-Amz-Algorithm only supports "AWS4-HMAC-SHA256"');
    }
    credential = q["X-Amz-Credential"] || "";
    signedHeaders = q["X-Amz-SignedHeaders"] || "";
    signature = q["X-Amz-Signature"] || "";
    amzDate = q["X-Amz-Date"] || "";
  } else {
    const match = AUTH4_RE.exec(pyStrip(headers.authorization || ""));
    if (!match) throw new S3Error("AuthorizationHeaderMalformed", "The authorization header is malformed.");
    [, credential, signedHeaders, signature] = match;
    amzDate = headers["x-amz-date"] || "";
  }
  const parts = credential.split("/");
  if (parts.length !== 5 || parts[4] !== "aws4_request") {
    throw new S3Error("AuthorizationHeaderMalformed", "The Credential is not valid.");
  }
  const [accessKey, day, region, service] = parts;
  if (!CREDENTIALS.has(accessKey)) {
    throw new S3Error("InvalidAccessKeyId", "The AWS Access Key Id you provided does not exist in our records.", 403, {
      AWSAccessKeyId: accessKey,
    });
  }
  const secret = CREDENTIALS.get(accessKey);
  let when = parseTime(amzDate);
  if (when === null && !presigned && headers.date) {
    when = parseTime(headers.date);
    amzDate = amzStamp(when || 0);
  }
  if (when === null) throw new S3Error("AccessDenied", "AWS authentication requires a valid Date or x-amz-date header", 403);
  const now = epoch();
  if (presigned) {
    let expires;
    try {
      expires = pyInt(q["X-Amz-Expires"] || "");
    } catch {
      throw new S3Error("AuthorizationQueryParametersError", "X-Amz-Expires must be a number.");
    }
    if (expires < 1 || expires > 604800) {
      throw new S3Error("AuthorizationQueryParametersError", "X-Amz-Expires must be between 1 and 604800 seconds.");
    }
    if (now > when + expires) {
      throw new S3Error("AccessDenied", "Request has expired", 403, { Expires: iso(when + expires), ServerTime: iso(now) });
    }
    if (when - now > SKEW) throw skewed();
  } else if (Math.abs(now - when) > SKEW) {
    throw skewed({ RequestTime: amzDate, ServerTime: iso(now) });
  }
  if (day !== amzDate.slice(0, 8) || !["s3", "s3-object-lambda"].includes(service)) {
    throw new S3Error("SignatureDoesNotMatch", "The credential scope does not match the request.", 403);
  }
  const names = signedHeaders.toLowerCase().split(";");
  if (!names.includes("host") || names.some((n) => headers[n] === undefined)) {
    throw new S3Error("SignatureDoesNotMatch", "SignedHeaders must include host and only headers that were sent.", 403);
  }
  let payload;
  if (presigned) {
    payload = headers["x-amz-content-sha256"] || q["X-Amz-Content-Sha256"] || "UNSIGNED-PAYLOAD";
  } else {
    payload = headers["x-amz-content-sha256"] || "";
    if (!payload) throw new S3Error("InvalidRequest", "Missing required header for this request: x-amz-content-sha256");
  }
  const canonicalHeaders = names.map((n) => `${n}:${pySplit(headers[n]).join(" ")}\n`).join("");
  const query = canonicalQuery(pairs, presigned ? "X-Amz-Signature" : "");
  const scope = `${day}/${region}/${service}/aws4_request`;
  const key = signingKey(secret, day, region, service);
  for (const p of canonicalPaths(rawPath)) {
    const canonical = [method, p, query, canonicalHeaders, signedHeaders.toLowerCase(), payload].join("\n");
    const toSign = ["AWS4-HMAC-SHA256", amzDate, scope, sha256Hex(Buffer.from(canonical, "utf8"))].join("\n");
    if (safeEqual(crypto.createHmac("sha256", key).update(toSign, "utf8").digest("hex"), signature)) {
      const auth = new Auth(accessKey, "sigv4");
      Object.assign(auth, { payload, key, signature, amzDate, scope, via: presigned ? "REST-QUERY-STRING" : "REST-HEADER" });
      return auth;
    }
  }
  throw new S3Error("SignatureDoesNotMatch",
    "The request signature we calculated does not match the signature you provided. Check your key and signing method.",
    403, { AWSAccessKeyId: accessKey });
}

function verifyV2(method, rawPath, rawQuery, headers, bucketVhost, presigned) {
  const q = Object.fromEntries(splitQuery(rawQuery));
  let accessKey;
  let signature;
  let date;
  if (presigned) {
    accessKey = q.AWSAccessKeyId || "";
    signature = q.Signature || "";
    date = q.Expires || "";
    let expires;
    try {
      expires = pyInt(date);
    } catch {
      throw new S3Error("AccessDenied", "Expires is not valid.", 403);
    }
    if (epoch() > expires) throw new S3Error("AccessDenied", "Request has expired", 403);
  } else {
    const value = (headers.authorization || "").slice(4);
    const colon = value.lastIndexOf(":");
    accessKey = colon < 0 ? "" : value.slice(0, colon);
    signature = colon < 0 ? value : value.slice(colon + 1);
    date = headers["x-amz-date"] !== undefined ? "" : headers.date || "";
    const when = parseTime(headers["x-amz-date"] || headers.date || "");
    if (when === null || Math.abs(epoch() - when) > SKEW) throw skewed();
  }
  if (!CREDENTIALS.has(accessKey)) {
    throw new S3Error("InvalidAccessKeyId", "The AWS Access Key Id you provided does not exist in our records.", 403);
  }
  const secret = CREDENTIALS.get(accessKey);
  const amz = Object.keys(headers).filter((k) => k.startsWith("x-amz-")).sort(cmpStr)
    .map((k) => [k, pySplit(headers[k]).join(" ")]);
  const resource = (bucketVhost ? `/${bucketVhost}` : "") + rawPath;
  const subs = rawQuery.split("&").filter((p) => {
    if (!p) return false;
    const at = p.indexOf("=");
    return V2_SUBRESOURCES.has(unquote(at < 0 ? p : p.slice(0, at)));
  }).sort(cmpStr);
  let query = "";
  if (subs.length) {
    query = `?${subs.map((s) => {
      const at = s.indexOf("=");
      return at < 0 ? unquote(s) : `${s.slice(0, at)}=${unquote(s.slice(at + 1))}`;
    }).join("&")}`;
  }
  let head = `${[method, headers["content-md5"] || "", headers["content-type"] || "", date].join("\n")}\n`;
  head += amz.map(([k, v]) => `${k}:${v}\n`).join("");
  // A bucket's resource is signed as /bucket or /bucket/ depending on the client.
  const slashes = (resource.match(/\//g) || []).length;
  const paths = [resource].concat(slashes === 1 ? [`${resource}/`] : resource.endsWith("/") ? [resource.replace(/\/+$/, "")] : []);
  const toSign = head + resource + query;
  const ok = paths.some((candidate) => {
    const digest = crypto.createHmac("sha1", Buffer.from(secret, "utf8")).update(head + candidate + query, "utf8").digest();
    return safeEqual(digest.toString("base64"), signature);
  });
  if (!ok) {
    throw new S3Error("SignatureDoesNotMatch", "The request signature we calculated does not match the signature you provided.",
      403, { AWSAccessKeyId: accessKey, StringToSign: toSign });
  }
  const auth = new Auth(accessKey, "sigv2");
  auth.payload = "UNSIGNED-PAYLOAD";
  auth.via = presigned ? "REST-QUERY-STRING" : "REST-HEADER";
  return auth;
}

/** A presigned URL (SigV4, path style). `extra` holds more query parameters to sign, as [name, value] pairs. */
function presign(method, host, bucket, key, expires, accessKey, scheme = "http", extra = []) {
  const secret = CREDENTIALS.get(accessKey) || "";
  const amzDate = amzStamp(epoch());
  const day = amzDate.slice(0, 8);
  const objectPath = `/${uriEncode(bucket)}/${uriEncode(key, "/-_.~")}`;
  const pairs = [
    ["X-Amz-Algorithm", "AWS4-HMAC-SHA256"],
    ["X-Amz-Credential", `${accessKey}/${day}/${REGION}/s3/aws4_request`],
    ["X-Amz-Date", amzDate],
    ["X-Amz-Expires", String(expires)],
    ["X-Amz-SignedHeaders", "host"],
  ];
  pairs.push(...extra);
  const query = canonicalQuery(pairs);
  const canonical = [method, objectPath, query, `host:${host}\n`, "host", "UNSIGNED-PAYLOAD"].join("\n");
  const scope = `${day}/${REGION}/s3/aws4_request`;
  const toSign = ["AWS4-HMAC-SHA256", amzDate, scope, sha256Hex(Buffer.from(canonical, "utf8"))].join("\n");
  const signature = crypto.createHmac("sha256", signingKey(secret, day, REGION, "s3")).update(toSign, "utf8").digest("hex");
  return `${scheme}://${host}${objectPath}?${query}&X-Amz-Signature=${signature}`;
}

module.exports = { presign, Auth, Received, wantedChecksum, receive, signingKey, verifyV4, verifyV2 };
