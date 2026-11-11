"use strict";
// Object requests: get / head / put / copy / delete and the object subresources; multipart goes to ./multipart.

const { asciiStrip, g, nullObj, own, pyInt, pyStrip, truthy } = require("../py");
const { S3Error, denied, invalid, malformed, noKey, notAllowed, preconditionFailed } = require("../errors");
const { ARCHIVED } = require("../config");
const { epoch, httpDate, iso, parseTime, parseXml, text, x } = require("../util");
const { checksumElement, checksumHeader } = require("../checksums");
const { getStore, unlink } = require("../store");
const { wantedChecksum } = require("../sigv4");
const { aclFromRequest, aclPublic, aclXml, bucketOwnerEnforced, needAuth, objectAction, publicBlock } = require("../access");
const { lockConfig } = require("../objectlock");
const {
  abortUpload, checkConditions, copyFile, deleteObject, findVersion, newVersion, objectFields, objectHeaders,
  parseRange, parseTagging, putVersion, readSource, sseHeaders, tagsFromXml, tagsXml,
} = require("../versions");
const { Response, xmlResponse } = require("../http");
const { completeUpload, createUpload, listParts, uploadPart } = require("./multipart");

const OBJECT_SUBRESOURCES = ["acl", "tagging", "retention", "legal-hold", "attributes", "restore", "uploads", "uploadId",
  "select", "torrent"];

async function objectRoute(req) {
  const q = req.q;
  const method = req.method;
  const bucket = getStore().get(req.bucket);
  const sub = OBJECT_SUBRESOURCES.find((s) => q[s] !== undefined) || "";
  if (sub === "select" || sub === "torrent") {
    throw new S3Error("NotImplemented", `${sub === "select" ? "SelectObjectContent" : "GetObjectTorrent"} is not implemented.`, 501);
  }
  if (method === "POST" && sub === "uploads") {
    needAuth(req, bucket, "s3:PutObject", req.key);
    return createUpload(req, bucket);
  }
  if (q.uploadId !== undefined) {
    const uploadId = q.uploadId;
    if (method === "PUT" && q.partNumber !== undefined) {
      needAuth(req, bucket, "s3:PutObject", req.key);
      return uploadPart(req, bucket, uploadId);
    }
    if (method === "POST") {
      needAuth(req, bucket, "s3:PutObject", req.key);
      return completeUpload(req, bucket, uploadId);
    }
    if (method === "DELETE") {
      needAuth(req, bucket, "s3:AbortMultipartUpload", req.key);
      if (!bucket.uploads.has(uploadId)) throw new S3Error("NoSuchUpload", "The specified upload does not exist.", 404, { UploadId: uploadId });
      abortUpload(bucket, uploadId);
      return new Response(204);
    }
    if (method === "GET") {
      needAuth(req, bucket, "s3:ListMultipartUploadParts", req.key);
      return listParts(req, bucket, uploadId);
    }
  }
  if (sub === "tagging") return objectTagging(req, bucket);
  if (sub === "acl") return objectAcl(req, bucket);
  if (sub === "retention" || sub === "legal-hold") return objectLockRoute(req, bucket, sub);
  if (sub === "attributes" && method === "GET") return objectAttributes(req, bucket);
  if (sub === "restore" && method === "POST") return restoreObject(req, bucket);
  if (method === "GET" || method === "HEAD") return getObject(req, bucket);
  if (method === "PUT") {
    needAuth(req, bucket, "s3:PutObject", req.key);
    return req.headers["x-amz-copy-source"] !== undefined ? copyObject(req, bucket) : putObject(req, bucket);
  }
  if (method === "DELETE") {
    needAuth(req, bucket, "s3:DeleteObject", req.key);
    return deleteRoute(req, bucket);
  }
  throw notAllowed();
}

const versionIdOf = (req) => (req.q.versionId !== undefined ? req.q.versionId : null);

/** HTML, XHTML, XML or SVG: content a browser could run scripts from. */
function activeContent(ctype) {
  const media = String(ctype || "").split(";")[0].trim().toLowerCase();
  return media === "text/html" || media.endsWith("/xml") || media.endsWith("+xml");
}

/** Pages opened from a bucket run in an opaque origin, away from the console's session. */
const SANDBOX = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads";

function getObject(req, bucket) {
  const versionId = versionIdOf(req);
  let version = findVersion(bucket, req.key, versionId);
  needAuth(req, bucket, versionId !== null && versionId ? "s3:GetObjectVersion" : "s3:GetObject", req.key, version);
  version = { ...version };
  const file = bucket.blobPath(version.blob);
  if (bucket.meta.versioning) version.versioned = true;
  const sseC = g(truthy(version.sse) ? version.sse : {}, "x-amz-server-side-encryption-customer-key-md5");
  if (sseC && req.headers["x-amz-server-side-encryption-customer-key-md5"] !== sseC) {
    throw new S3Error("InvalidRequest",
      "The object was stored using a form of Server Side Encryption. The correct parameters must be provided to retrieve the object.");
  }
  try {
    checkConditions(version, req.headers);
  } catch (err) {
    if (err instanceof S3Error && err.status === 304) err.headers = { ETag: `"${version.etag}"`, "Last-Modified": httpDate(version.time) };
    throw err;
  }
  if (ARCHIVED.includes(version.class) && req.method === "GET") {
    if (!version.restore || version.restore < epoch()) {
      throw new S3Error("InvalidObjectState", "The operation is not valid for the object's storage class", 403, { StorageClass: version.class });
    }
  }
  const size = pyInt(version.size);
  const part = req.q.partNumber;
  let rng = null;
  const headers = objectHeaders(version, (req.headers["x-amz-checksum-mode"] || "").toUpperCase() === "ENABLED");
  if (part) {
    let n;
    try {
      n = pyInt(part);
    } catch {
      throw invalid("Part number must be an integer between 1 and 10000, inclusive", "partNumber", part);
    }
    const parts = truthy(version.parts) ? version.parts : [{ size }];
    if (n < 1 || n > parts.length) throw new S3Error("InvalidPartNumber", "The requested partnumber is not satisfiable", 416);
    const start = parts.slice(0, n - 1).reduce((t, p) => t + pyInt(p.size), 0);
    rng = parts[n - 1].size ? [start, start + pyInt(parts[n - 1].size) - 1] : null;
    headers["x-amz-mp-parts-count"] = String(parts.length);
    if (rng === null) headers["Content-Range"] = `bytes */${size}`;
  } else if (req.headers.range) {
    rng = parseRange(req.headers.range, size);
  }
  for (const name of ["content-type", "content-language", "expires", "cache-control", "content-disposition", "content-encoding"]) {
    const override = req.q[`response-${name}`];
    if (override !== undefined) {
      if (req.who === null) {
        throw new S3Error("InvalidRequest", "Request specific response headers cannot be used for anonymous GET requests.");
      }
      const proper = name.split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join("-");
      delete headers[name];
      headers[name !== "content-type" ? proper : "Content-Type"] = override;
    }
  }
  if (req.method === "GET" && !req.vhost && activeContent(headers["Content-Type"])) {
    // Path-style URLs share the console's origin: a page from a bucket runs in an opaque origin.
    headers["Content-Security-Policy"] = SANDBOX;
  }
  if (rng !== null) {
    for (const h of Object.keys(headers)) if (h.startsWith("x-amz-checksum-")) delete headers[h];
    const [start, end] = rng;
    headers["Content-Range"] = `bytes ${start}-${end}/${size}`;
    return new Response(206, Buffer.alloc(0), headers, headers["Content-Type"] || "binary/octet-stream", file, start, end - start + 1);
  }
  return new Response(200, Buffer.alloc(0), headers, headers["Content-Type"] || "binary/octet-stream", file, 0, size);
}

function writeHeaders(version, bucket) {
  const headers = { ETag: `"${version.etag}"` };
  if (bucket.meta.versioning) headers["x-amz-version-id"] = version.id;
  if (truthy(version.checksum)) {
    headers[checksumHeader(version.checksum.alg)] = version.checksum.value;
    headers["x-amz-checksum-type"] = "FULL_OBJECT";
  }
  return sseHeaders(version.sse, headers);
}

async function putObject(req, bucket) {
  if (req.headers["content-length"] === undefined && !(req.headers["transfer-encoding"] || "").includes("chunked") &&
    !req.headers["x-amz-decoded-content-length"]) {
    throw new S3Error("MissingContentLength", "You must provide the Content-Length HTTP header.", 411);
  }
  const fields = objectFields(req.headers, bucket);
  if ((req.headers["if-none-match"] !== undefined ? req.headers["if-none-match"] : "*") !== "*") {
    throw new S3Error("NotImplemented", "If-None-Match on a write only supports *.", 501);
  }
  const [alg, expected] = wantedChecksum(req.headers);
  const received = await req.payload(alg, expected);
  let version;
  try {
    const rec = bucket.objects.get(req.key);
    const current = rec && !rec.versions[0].dm ? rec.versions[0] : null;
    if (req.headers["if-none-match"] === "*" && current) throw preconditionFailed("If-None-Match");
    if (req.headers["if-match"]) {
      if (!current) throw noKey(req.key);
      checkConditions(current, { "if-match": req.headers["if-match"] }, "", true);
    }
    const blob = getStore().commitBlob(bucket, received.path);
    received.path = null;
    version = putVersion(bucket, req.key, newVersion(received, fields, blob));
  } finally {
    if (received.path) unlink(received.path);
  }
  return new Response(200, Buffer.alloc(0), writeHeaders(version, bucket));
}

async function copyObject(req, bucket) {
  const [srcBucket, srcKey, src, srcPath] = readSource(req);
  const directive = (req.headers["x-amz-metadata-directive"] || "COPY").toUpperCase();
  const tagDirective = (req.headers["x-amz-tagging-directive"] || "COPY").toUpperCase();
  if (!["COPY", "REPLACE"].includes(directive) || !["COPY", "REPLACE"].includes(tagDirective)) {
    throw invalid("Unknown metadata directive.", "x-amz-metadata-directive", directive);
  }
  const same = srcBucket === bucket && srcKey === req.key && !(req.headers["x-amz-copy-source"] || "").includes("versionId=");
  const changes = directive === "REPLACE" || ["x-amz-storage-class", "x-amz-server-side-encryption", "x-amz-website-redirect-location"]
    .some((h) => req.headers[h] !== undefined);
  if (same && !changes) {
    throw new S3Error("InvalidRequest", "This copy request is illegal because it is trying to copy an object to " +
      "itself without changing the object's metadata, storage class, website redirect location or encryption attributes.");
  }
  let fields;
  if (directive === "REPLACE") {
    fields = objectFields(req.headers, bucket);
  } else {
    const merged = Object.assign(nullObj(), req.headers);
    merged["content-type"] = src.type || "binary/octet-stream";
    for (const [k, v] of Object.entries(truthy(src.headers) ? src.headers : {})) merged[k] = v;
    for (const k of Object.keys(merged)) if (k.startsWith("x-amz-meta-")) delete merged[k];
    for (const [k, v] of Object.entries(truthy(src.meta) ? src.meta : {})) merged[`x-amz-meta-${k}`] = v;
    delete merged["x-amz-tagging"];
    fields = objectFields(merged, bucket);
  }
  if (tagDirective === "COPY") fields.tags = { ...(truthy(src.tags) ? src.tags : {}) };
  else if (req.headers["x-amz-tagging"]) fields.tags = parseTagging(req.headers["x-amz-tagging"]);
  else fields.tags = {};
  const alg = (req.headers["x-amz-checksum-algorithm"] || (truthy(src.checksum) ? src.checksum.alg : "") || "").toUpperCase();
  const received = await copyFile(srcPath, 0, pyInt(src.size) - 1, alg);
  let version;
  try {
    const blob = getStore().commitBlob(bucket, received.path);
    received.path = null;
    version = putVersion(bucket, req.key, newVersion(received, fields, blob));
  } finally {
    if (received.path) unlink(received.path);
  }
  const headers = {};
  if (src.id !== "null" || srcBucket.meta.versioning) headers["x-amz-copy-source-version-id"] = src.id;
  if (bucket.meta.versioning) headers["x-amz-version-id"] = version.id;
  let inner = x("LastModified", iso(version.time)) + x("ETag", `"${version.etag}"`);
  if (truthy(version.checksum)) inner += x("ChecksumType", "FULL_OBJECT") + x(checksumElement(version.checksum.alg), version.checksum.value);
  return xmlResponse("CopyObjectResult", inner, 200, headers);
}

function deleteRoute(req, bucket) {
  const versionId = versionIdOf(req);
  const bypass = (req.headers["x-amz-bypass-governance-retention"] || "").toLowerCase() === "true";
  if (req.headers["if-match"]) {
    const rec = bucket.objects.get(req.key);
    if (!rec || rec.versions[0].dm) throw noKey(req.key);
    checkConditions(rec.versions[0], { "if-match": req.headers["if-match"] }, "", true);
  }
  const result = deleteObject(bucket, req.key, versionId, bypass);
  const headers = {};
  if (result.marker) headers["x-amz-delete-marker"] = "true";
  if (result.id) headers["x-amz-version-id"] = result.id;
  return new Response(204, Buffer.alloc(0), headers);
}

async function objectTagging(req, bucket) {
  const versionId = versionIdOf(req);
  needAuth(req, bucket, objectAction("tagging", req.method, versionId !== null), req.key, null, true);
  let version = findVersion(bucket, req.key, versionId);
  const headers = bucket.meta.versioning ? { "x-amz-version-id": version.id } : {};
  if (req.method === "GET") return new Response(200, tagsXml(truthy(version.tags) ? version.tags : {}), headers);
  if (req.method === "PUT") {
    const tags = tagsFromXml(await req.smallBody());
    version = findVersion(bucket, req.key, versionId);
    version.tags = tags;
    bucket.saveRecord(req.key);
    return new Response(200, Buffer.alloc(0), headers);
  }
  if (req.method === "DELETE") {
    version = findVersion(bucket, req.key, versionId);
    version.tags = {};
    bucket.saveRecord(req.key);
    return new Response(204, Buffer.alloc(0), headers);
  }
  throw notAllowed();
}

async function objectAcl(req, bucket) {
  const versionId = versionIdOf(req);
  needAuth(req, bucket, objectAction("acl", req.method, versionId !== null), req.key, null, true);
  if (req.method === "GET") return new Response(200, aclXml(findVersion(bucket, req.key, versionId).acl));
  if (req.method === "PUT") {
    const acl = aclFromRequest(req.headers, await req.smallBody());
    if (!acl) throw malformed();
    if (bucketOwnerEnforced(bucket) && !["private", "bucket-owner-full-control"].includes(acl.canned)) {
      throw new S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs");
    }
    if (publicBlock(bucket).BlockPublicAcls && aclPublic(acl, "READ")) throw denied();
    const version = findVersion(bucket, req.key, versionId);
    version.acl = acl;
    bucket.saveRecord(req.key);
    return new Response(200);
  }
  throw notAllowed();
}

const noLockConfig = () =>
  new S3Error("NoSuchObjectLockConfiguration", "The specified object does not have a ObjectLock configuration", 404);

async function objectLockRoute(req, bucket, sub) {
  const versionId = versionIdOf(req);
  needAuth(req, bucket, objectAction(sub, req.method, versionId !== null), req.key, null, true);
  if (!lockConfig(bucket).enabled) throw new S3Error("InvalidRequest", "Bucket is missing Object Lock Configuration");
  if (req.method === "GET") {
    const version = findVersion(bucket, req.key, versionId);
    if (sub === "retention") {
      if (!truthy(version.retention)) throw noLockConfig();
      const r = version.retention;
      return xmlResponse("Retention", x("Mode", r.mode) + x("RetainUntilDate", iso(r.until)));
    }
    if (!own(version, "hold")) throw noLockConfig();
    return xmlResponse("LegalHold", x("Status", version.hold ? "ON" : "OFF"));
  }
  if (req.method === "PUT") {
    const root = parseXml(await req.smallBody());
    const bypass = (req.headers["x-amz-bypass-governance-retention"] || "").toLowerCase() === "true";
    const version = findVersion(bucket, req.key, versionId);
    if (sub === "legal-hold") {
      const status = text(root, "Status");
      if (status !== "ON" && status !== "OFF") throw malformed();
      version.hold = status === "ON";
    } else {
      const mode = text(root, "Mode");
      const until = parseTime(text(root, "RetainUntilDate"));
      if ((mode && !["GOVERNANCE", "COMPLIANCE"].includes(mode)) || (mode && until === null)) throw malformed();
      const old = truthy(version.retention) ? version.retention : {};
      if (g(old, "until", 0) > epoch()) {
        const shorter = !mode || (until || 0) < old.until || (old.mode === "COMPLIANCE" && mode !== "COMPLIANCE");
        if (shorter && (old.mode === "COMPLIANCE" || !bypass)) throw denied("Access Denied because object protected by object lock.");
      }
      if (mode) {
        if (until !== null && until <= epoch()) throw invalid("The retain until date must be in the future!");
        version.retention = { mode, until };
      } else {
        delete version.retention;
      }
    }
    bucket.saveRecord(req.key);
    return new Response(200);
  }
  throw notAllowed();
}

function objectAttributes(req, bucket) {
  const versionId = versionIdOf(req);
  needAuth(req, bucket, "s3:GetObject", req.key);
  const wanted = new Set((req.headers["x-amz-object-attributes"] || "").split(",").map((a) => pyStrip(a)).filter(Boolean));
  if (!wanted.size) {
    throw invalid("The x-amz-object-attributes header specifying the attributes to be retrieved is either missing or empty",
      "x-amz-object-attributes", "");
  }
  const version = { ...findVersion(bucket, req.key, versionId) };
  let inner = "";
  if (wanted.has("ETag")) inner += x("ETag", version.etag);
  if (wanted.has("Checksum") && truthy(version.checksum)) {
    const cs = version.checksum;
    inner += `<Checksum>${x(checksumElement(cs.alg), cs.value)}${x("ChecksumType", g(cs, "type", "FULL_OBJECT"))}</Checksum>`;
  }
  if (wanted.has("ObjectParts") && truthy(version.parts)) {
    const parts = version.parts;
    const marker = pyInt(req.q["part-number-marker"] || req.headers["x-amz-part-number-marker"] || "0");
    const maxParts = pyInt(req.headers["x-amz-max-parts"] || "1000");
    const after = parts.map((p, i) => [i + 1, p]).filter(([n]) => n > marker);
    const chosen = after.slice(0, Math.max(0, maxParts < 0 ? after.length + maxParts : maxParts));
    const more = after.length > maxParts;
    let items = "";
    for (const [n, p] of chosen) {
      items += `<Part>${x("PartNumber", n)}${x("Size", p.size)}`;
      if (p.checksum && truthy(version.checksum)) items += x(checksumElement(version.checksum.alg), p.checksum);
      items += "</Part>";
    }
    inner += `<ObjectParts>${x("TotalPartsCount", parts.length)}${x("PartNumberMarker", marker)}` +
      `${x("NextPartNumberMarker", chosen.length ? chosen[chosen.length - 1][0] : marker)}${x("MaxParts", maxParts)}` +
      `${x("IsTruncated", more ? "true" : "false")}${items}</ObjectParts>`;
  }
  if (wanted.has("StorageClass")) inner += x("StorageClass", g(version, "class", "STANDARD"));
  if (wanted.has("ObjectSize")) inner += x("ObjectSize", version.size);
  const headers = { "Last-Modified": httpDate(version.time) };
  if (bucket.meta.versioning) headers["x-amz-version-id"] = version.id;
  return xmlResponse("GetObjectAttributesResponse", inner, 200, headers);
}

async function restoreObject(req, bucket) {
  const versionId = versionIdOf(req);
  needAuth(req, bucket, objectAction("restore", req.method, versionId !== null), req.key, null, true);
  const body = await req.smallBody();
  let days = 1;
  if (asciiStrip(body.toString("latin1"))) {
    const root = parseXml(body);
    if (text(root, "Type") === "SELECT") throw new S3Error("NotImplemented", "S3 Select restore requests are not implemented.", 501);
    days = pyInt(text(root, "Days") || "1");
  }
  const version = findVersion(bucket, req.key, versionId);
  if (!ARCHIVED.includes(version.class)) {
    throw new S3Error("InvalidObjectState", "Restore is not allowed for the object's current storage class", 403);
  }
  const already = Boolean(version.restore) && version.restore > epoch();
  version.restore = epoch() + days * 86400;
  bucket.saveRecord(req.key);
  return new Response(already ? 200 : 202);
}

module.exports = { objectRoute };
