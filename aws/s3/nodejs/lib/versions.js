"use strict";
// Buckets, objects and versions: create / delete buckets, find / put / remove versions and delete markers, tags,
// object fields and headers, conditional requests, ranges, copy sources and key listing.

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { bisectLeft, bisectRight, cmpStr, g, own, pyLen, pyStrip, truthy } = require("./py");
const { S3Error, denied, invalid, noKey, preconditionFailed } = require("./errors");
const { ARCHIVED, NS, OWNER_ID, STD_HEADERS, STORAGE_CLASSES } = require("./config");
const {
  UTF8_STRICT, doc, epoch, esc, httpDate, iso, log, now3, parseTime, parseXml, splitQuery, text, unquote, x,
} = require("./util");
const { b64decodeLoose, checksumHeader, newChecksum } = require("./checksums");
const { Bucket, configsOf, getStore, rmTree, unlink } = require("./store");
const { Received } = require("./sigv4");
const { aclFromRequest, aclPublic, bucketOwnerEnforced, needAuth, publicBlock } = require("./access");
const { checkUnlocked, lockConfig } = require("./objectlock");

const BUCKET_RE = /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/;
const IP_RE = /^\d+\.\d+\.\d+\.\d+$/;
const newVersionId = () => crypto.randomBytes(24).toString("base64url").replace(/-/g, ".");

function createBucket(name, region, acl, objectLock, ownership = "") {
  if (!BUCKET_RE.test(name) || name.includes("..") || IP_RE.test(name) || name.startsWith("xn--") ||
    name.endsWith("-s3alias") || name.endsWith("--ol-s3")) {
    throw new S3Error("InvalidBucketName", "The specified bucket is not valid.", 400, { BucketName: name });
  }
  if (getStore().buckets.has(name)) {
    throw new S3Error("BucketAlreadyOwnedByYou", "Your previous request to create the named bucket succeeded and you already own it.",
      409, { BucketName: name });
  }
  const meta = {
    name,
    created: now3(),
    region,
    versioning: "",
    mfa_delete: "",
    object_lock: objectLock,
    acl: acl || { canned: "private" },
    tags: {},
    policy: null,
    configs: {},
    ids: {},
  };
  if (objectLock) {
    meta.versioning = "Enabled";
    meta.configs["object-lock"] = `<ObjectLockConfiguration xmlns="${NS}"><ObjectLockEnabled>Enabled</ObjectLockEnabled></ObjectLockConfiguration>`;
  }
  if (ownership) {
    meta.configs.ownershipControls = `<OwnershipControls xmlns="${NS}"><Rule><ObjectOwnership>${esc(ownership)}</ObjectOwnership></Rule></OwnershipControls>`;
  }
  const bucket = new Bucket(path.join(getStore().root, "buckets", name), meta);
  bucket.saveMeta();
  getStore().buckets.set(name, bucket);
  log("bucket created", name);
  return bucket;
}

function deleteBucket(name) {
  const bucket = getStore().get(name);
  if (bucket.objects.size) throw new S3Error("BucketNotEmpty", "The bucket you tried to delete is not empty", 409, { BucketName: name });
  for (const uploadId of [...bucket.uploads.keys()]) abortUpload(bucket, uploadId);
  getStore().buckets.delete(name);
  rmTree(bucket.path);
  log("bucket deleted", name);
}

function findVersion(bucket, key, versionId, allowMarker = false) {
  const rec = bucket.objects.get(key);
  if (versionId !== null && versionId !== undefined) {
    if (versionId === "") throw invalid("Version id cannot be the empty string", "versionId", "");
    for (const version of rec ? rec.versions : []) {
      if (version.id === versionId) {
        if (version.dm && !allowMarker) {
          const err = new S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405, {
            Method: "GET",
            ResourceType: "DeleteMarker",
          });
          err.headers = { "x-amz-delete-marker": "true", "x-amz-version-id": versionId, "Last-Modified": httpDate(version.time) };
          throw err;
        }
        return version;
      }
    }
    if (!rec && !/^[A-Za-z0-9._=-]+$/.test(versionId)) throw invalid("Invalid version id specified", "versionId", versionId);
    throw new S3Error("NoSuchVersion", "The specified version does not exist.", 404, { Key: key, VersionId: versionId });
  }
  if (!rec) throw noKey(key);
  const latest = rec.versions[0];
  if (latest.dm) {
    const err = noKey(key);
    err.headers = { "x-amz-delete-marker": "true", "x-amz-version-id": latest.id };
    throw err;
  }
  return latest;
}

function removeVersion(bucket, key, versionId) {
  const rec = bucket.objects.get(key);
  if (!rec) return null;
  const idx = rec.versions.findIndex((v) => v.id === versionId);
  if (idx < 0) return null;
  const [version] = rec.versions.splice(idx, 1);
  bucket.saveRecord(key);
  if (version.blob) unlink(bucket.blobPath(version.blob));
  return version;
}

/** Make `version` the newest version of `key`, under the bucket's versioning state. */
function putVersion(bucket, key, version) {
  const rec = bucket.objects.get(key) || { key, versions: [] };
  if (bucket.meta.versioning === "Enabled") {
    version.id = newVersionId();
  } else {
    version.id = "null";
    for (const old of rec.versions.filter((v) => v.id === "null")) {
      rec.versions.splice(rec.versions.indexOf(old), 1);
      if (old.blob) unlink(bucket.blobPath(old.blob));
    }
  }
  rec.versions.unshift(version);
  bucket.setRecord(key, rec);
  return version;
}

/** {marker: bool, id: version id or ""}. */
function deleteObject(bucket, key, versionId, bypass) {
  const rec = bucket.objects.get(key);
  if (versionId !== null && versionId !== undefined) {
    for (const version of rec ? rec.versions : []) {
      if (version.id === versionId) {
        if (!version.dm) checkUnlocked(version, bypass);
        removeVersion(bucket, key, versionId);
        return { marker: truthy(version.dm), id: versionId };
      }
    }
    return { marker: false, id: versionId };
  }
  if (!bucket.meta.versioning) {
    if (rec) for (const version of [...rec.versions]) removeVersion(bucket, key, version.id);
    return { marker: false, id: "" };
  }
  const marker = { dm: true, time: now3(), owner: OWNER_ID };
  putVersion(bucket, key, marker);
  return { marker: true, id: marker.id };
}

function abortUpload(bucket, uploadId) {
  bucket.uploads.delete(uploadId);
  rmTree(bucket.uploadDir(uploadId));
}

function parseTagging(raw) {
  const tags = {};
  for (const [k, v] of splitQuery(raw.replace(/\+/g, "%20"))) tags[k] = v;
  validateTags(tags);
  return tags;
}

function validateTags(tags, limit = 10) {
  if (Object.keys(tags).length > limit) throw new S3Error("InvalidTag", `Object tags cannot be greater than ${limit}`);
  for (const [k, v] of Object.entries(tags)) {
    if (!k || [...k].length > 128) throw new S3Error("InvalidTag", "The TagKey you have provided is invalid");
    if ([...v].length > 256) throw new S3Error("InvalidTag", "The TagValue you have provided is too long");
    if (k.toLowerCase().startsWith("aws:")) throw new S3Error("InvalidTag", "Your TagKey cannot be prefixed with aws:");
  }
}

function tagsFromXml(body, limit = 10) {
  const root = parseXml(body);
  const tags = {};
  for (const tag of root.iter("Tag")) {
    const key = text(tag, "Key");
    if (own(tags, key)) throw new S3Error("InvalidTag", "Cannot provide multiple Tags with the same key");
    tags[key] = text(tag, "Value");
  }
  validateTags(tags, limit);
  return tags;
}

function tagsXml(tags) {
  const inner = Object.keys(tags).sort(cmpStr).map((k) => `<Tag>${x("Key", k)}${x("Value", tags[k])}</Tag>`).join("");
  return doc("Tagging", `<TagSet>${inner}</TagSet>`);
}

const SSE_HEADERS = ["x-amz-server-side-encryption", "x-amz-server-side-encryption-aws-kms-key-id",
  "x-amz-server-side-encryption-context", "x-amz-server-side-encryption-bucket-key-enabled",
  "x-amz-server-side-encryption-customer-algorithm", "x-amz-server-side-encryption-customer-key-md5"];

/** The stored attributes of a new object from its request headers (PutObject, CreateMultipartUpload, copy). */
function objectFields(headers, bucket) {
  const meta = {};
  for (const [k, v] of Object.entries(headers)) if (k.startsWith("x-amz-meta-")) meta[k.slice(11)] = v;
  if (Object.entries(meta).reduce((n, [k, v]) => n + pyLen(k) + pyLen(v), 0) > 2048) {
    throw new S3Error("MetadataTooLarge", "Your metadata headers exceed the maximum allowed metadata size.");
  }
  const std = {};
  for (const k of STD_HEADERS) if (headers[k] !== undefined) std[k] = headers[k];
  const sclass = (headers["x-amz-storage-class"] !== undefined ? headers["x-amz-storage-class"] : "STANDARD") || "STANDARD";
  if (!STORAGE_CLASSES.includes(sclass)) {
    throw new S3Error("InvalidStorageClass", "The storage class you specified is not valid", 400, { StorageClassRequested: sclass });
  }
  const fields = {
    type: headers["content-type"] || "binary/octet-stream",
    meta,
    headers: std,
    class: sclass,
    tags: headers["x-amz-tagging"] ? parseTagging(headers["x-amz-tagging"]) : {},
    owner: OWNER_ID,
  };
  const acl = aclFromRequest(headers, Buffer.alloc(0));
  if (acl) {
    if (bucketOwnerEnforced(bucket) && !["bucket-owner-full-control", "private"].includes(acl.canned)) {
      throw new S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs");
    }
    if (publicBlock(bucket).BlockPublicAcls && aclPublic(acl, "READ")) throw denied();
    fields.acl = acl;
  }
  const redirect = headers["x-amz-website-redirect-location"];
  if (redirect) fields.redirect = redirect;
  let sse = {};
  for (const name of SSE_HEADERS) if (headers[name]) sse[name] = headers[name];
  if (!Object.keys(sse).length) sse = defaultEncryption(bucket);
  fields.sse = sse;
  const lock = lockConfig(bucket);
  const mode = headers["x-amz-object-lock-mode"] || "";
  const until = headers["x-amz-object-lock-retain-until-date"] || "";
  const hold = headers["x-amz-object-lock-legal-hold"] || "";
  if ((mode || until || hold) && !lock.enabled) throw new S3Error("InvalidRequest", "Bucket is missing Object Lock Configuration");
  if (mode || until) {
    if (!["GOVERNANCE", "COMPLIANCE"].includes(mode) || parseTime(until) === null) {
      throw invalid("x-amz-object-lock-mode and x-amz-object-lock-retain-until-date must both be supplied");
    }
    fields.retention = { mode, until: parseTime(until) };
  } else if (lock.enabled && lock.mode) {
    const period = lock.days * 86400 + lock.years * 365 * 86400;
    fields.retention = { mode: lock.mode, until: epoch() + period };
  }
  if (hold) fields.hold = hold === "ON";
  return fields;
}

function defaultEncryption(bucket) {
  const raw = g(configsOf(bucket), "encryption", "");
  if (raw) {
    try {
      const root = parseXml(Buffer.from(raw, "utf8"));
      const alg = text(root, "Rule/ApplyServerSideEncryptionByDefault/SSEAlgorithm") || "AES256";
      const out = { "x-amz-server-side-encryption": alg };
      const kms = text(root, "Rule/ApplyServerSideEncryptionByDefault/KMSMasterKeyID");
      if (kms) out["x-amz-server-side-encryption-aws-kms-key-id"] = kms;
      if (text(root, "Rule/BucketKeyEnabled").toLowerCase() === "true") out["x-amz-server-side-encryption-bucket-key-enabled"] = "true";
      return out;
    } catch (err) {
      if (!(err instanceof S3Error)) throw err;
    }
  }
  return { "x-amz-server-side-encryption": "AES256" };
}

function sseHeaders(sse, into = {}) {
  for (const [k, v] of Object.entries(truthy(sse) ? sse : {})) if (k !== "x-amz-server-side-encryption-context") into[k] = v;
  return into;
}

function objectHeaders(version, checksum = false) {
  const h = {
    ETag: `"${version.etag}"`,
    "Last-Modified": httpDate(version.time),
    "Content-Type": version.type || "binary/octet-stream",
    "Accept-Ranges": "bytes",
  };
  if (version.id !== "null" || truthy(version.versioned)) h["x-amz-version-id"] = version.id;
  for (const [k, v] of Object.entries(truthy(version.headers) ? version.headers : {})) h[k] = v;
  for (const [k, v] of Object.entries(truthy(version.meta) ? version.meta : {})) h[`x-amz-meta-${k}`] = v;
  if (g(version, "class", "STANDARD") !== "STANDARD") h["x-amz-storage-class"] = version.class;
  if (truthy(version.tags)) h["x-amz-tagging-count"] = String(Object.keys(version.tags).length);
  if (version.redirect) h["x-amz-website-redirect-location"] = version.redirect;
  sseHeaders(version.sse, h);
  if (truthy(version.retention)) {
    h["x-amz-object-lock-mode"] = version.retention.mode;
    h["x-amz-object-lock-retain-until-date"] = iso(version.retention.until);
  }
  if (own(version, "hold")) h["x-amz-object-lock-legal-hold"] = version.hold ? "ON" : "OFF";
  if (truthy(version.parts)) h["x-amz-mp-parts-count"] = String(version.parts.length);
  if (ARCHIVED.includes(version.class) && version.restore) {
    h["x-amz-restore"] = `ongoing-request="false", expiry-date="${httpDate(version.restore)}"`;
  }
  if (checksum && truthy(version.checksum)) {
    const cs = version.checksum;
    h[checksumHeader(cs.alg)] = cs.value;
    h["x-amz-checksum-type"] = g(cs, "type", "FULL_OBJECT");
  }
  return h;
}

/** If-Match / If-None-Match / If-(Un)Modified-Since, AWS's precedence. `prefix` is "x-amz-copy-source-". */
function checkConditions(version, headers, prefix = "", write = false) {
  const etag = `"${version.etag}"`;
  const modified = Math.trunc(version.time);
  const ifMatch = headers[prefix + "if-match"];
  const ifNone = headers[prefix + "if-none-match"];
  const ifMod = parseTime(headers[prefix + "if-modified-since"] || "");
  const ifUnmod = parseTime(headers[prefix + "if-unmodified-since"] || "");
  const matches = (value) => value.split(",").some((t) => ["*", etag, version.etag].includes(pyStrip(t)));
  if (ifMatch !== undefined && !matches(ifMatch)) throw preconditionFailed("If-Match");
  if (ifUnmod !== null && ifMatch === undefined && modified > ifUnmod) throw preconditionFailed("If-Unmodified-Since");
  if (ifNone !== undefined && matches(ifNone)) {
    if (prefix || write) throw preconditionFailed("If-None-Match");
    throw new S3Error("NotModified", "Not Modified", 304);
  }
  if (ifMod !== null && ifNone === undefined && modified <= ifMod) {
    if (prefix) throw preconditionFailed("If-Modified-Since");
    throw new S3Error("NotModified", "Not Modified", 304);
  }
}

function parseRange(value, size) {
  const match = /^\s*bytes=(\d*)-(\d*)\s*$/.exec(value || "");
  if (!match || (!match[1] && !match[2])) return null; // S3 ignores a Range it cannot parse
  const [, first, last] = match;
  const unsatisfiable = (actual) => new S3Error("InvalidRange", "The requested range is not satisfiable", 416, {
    RangeRequested: value,
    ActualObjectSize: actual,
  });
  let start;
  let end;
  if (first) {
    start = Number(first);
    end = last ? Math.min(Number(last), size - 1) : size - 1;
    if (start >= size || (last && Number(last) < start)) throw unsatisfiable(String(size));
  } else {
    const suffix = Number(last);
    if (suffix === 0) throw unsatisfiable(String(size));
    start = Math.max(0, size - suffix);
    end = size - 1;
  }
  if (size === 0) throw unsatisfiable("0");
  return [start, end];
}

function newVersion(received, fields, blob) {
  const version = { ...fields, blob, size: received.size, etag: received.md5, time: now3() };
  if (received.checksum) version.checksum = { alg: received.checksum[0], value: received.checksum[1], type: "FULL_OBJECT" };
  return version;
}

function copySource(headers) {
  const raw = headers["x-amz-copy-source"] || "";
  const qi = raw.indexOf("?");
  const query = qi < 0 ? "" : raw.slice(qi + 1);
  const srcPath = unquote(qi < 0 ? raw : raw.slice(0, qi)).replace(/^\/+/, "");
  if (srcPath.startsWith("arn:")) throw new S3Error("NotImplemented", "Copying from an access point is not supported.", 501);
  const slash = srcPath.indexOf("/");
  const srcBucket = slash < 0 ? srcPath : srcPath.slice(0, slash);
  const srcKey = slash < 0 ? "" : srcPath.slice(slash + 1);
  if (!srcBucket || !srcKey) {
    throw invalid("Copy Source must mention the source bucket and key: sourcebucket/sourcekey", "x-amz-copy-source", raw);
  }
  let versionId = null;
  for (const [k, v] of splitQuery(query)) if (k === "versionId") versionId = v;
  return [srcBucket, srcKey, versionId];
}

/** The source of a copy (x-amz-copy-source), which the requester must be allowed to read: [bucket, key, version, file]. */
function readSource(req) {
  const headers = req.headers;
  const [srcBucketName, srcKey, srcVid] = copySource(headers);
  const srcBucket = getStore().get(srcBucketName);
  const version = findVersion(srcBucket, srcKey, srcVid);
  needAuth(req, srcBucket, "s3:GetObject", srcKey, version);
  if (ARCHIVED.includes(version.class) && !version.restore) {
    throw new S3Error("InvalidObjectState", "The operation is not valid for the object's storage class", 403, {
      StorageClass: version.class,
    });
  }
  checkConditions(version, headers, "x-amz-copy-source-");
  return [srcBucket, srcKey, { ...version }, srcBucket.blobPath(version.blob)];
}

async function copyFile(src, start, end, alg) {
  const out = new Received();
  out.path = getStore().tempFile();
  const md5 = crypto.createHash("md5");
  const hasher = alg ? newChecksum(alg) : null;
  const fin = await fs.promises.open(src, "r");
  let fout = null;
  try {
    fout = await fs.promises.open(out.path, "w");
    const buf = Buffer.alloc(1024 * 1024);
    let pos = start;
    let left = end - start + 1;
    while (left > 0) {
      const { bytesRead } = await fin.read(buf, 0, Math.min(buf.length, left), pos);
      if (!bytesRead) break;
      const data = buf.subarray(0, bytesRead);
      left -= bytesRead;
      pos += bytesRead;
      md5.update(data);
      if (hasher) hasher.update(data);
      await fout.write(data);
      out.size += bytesRead;
    }
  } catch (err) {
    if (fout) await fout.close().catch(() => {});
    fout = null;
    unlink(out.path);
    throw err;
  } finally {
    await fin.close().catch(() => {});
    if (fout) await fout.close();
  }
  out.md5 = md5.digest("hex");
  if (hasher) out.checksum = [alg, hasher.digest().toString("base64")];
  return out;
}

function listKeys(bucket, prefix, delimiter, after, maxKeys, include) {
  const keys = bucket.keys();
  let i = bisectLeft(keys, prefix);
  if (after) {
    i = Math.max(i, bisectRight(keys, after));
    if (delimiter && after.endsWith(delimiter)) while (i < keys.length && keys[i].startsWith(after)) i += 1;
  }
  const contents = [];
  const prefixes = [];
  let last = "";
  let count = 0;
  let truncated = false;
  while (i < keys.length) {
    const key = keys[i];
    if (!key.startsWith(prefix)) break;
    if (!include(key)) {
      i += 1;
      continue;
    }
    if (delimiter) {
      const pos = key.indexOf(delimiter, prefix.length);
      if (pos >= 0) {
        const common = key.slice(0, pos + delimiter.length);
        if (count >= maxKeys) {
          truncated = true;
          break;
        }
        prefixes.push(common);
        last = common;
        count += 1;
        while (i < keys.length && keys[i].startsWith(common)) i += 1;
        continue;
      }
    }
    if (count >= maxKeys) {
      truncated = true;
      break;
    }
    contents.push(key);
    last = key;
    count += 1;
    i += 1;
  }
  return [contents, prefixes, truncated, last];
}

function tokenEncode(value) {
  const b = Buffer.from(value, "utf8").toString("base64url");
  return b + "=".repeat((4 - (b.length % 4)) % 4);
}

function tokenDecode(value) {
  try {
    const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
    return UTF8_STRICT.decode(b64decodeLoose(padded.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    throw invalid("The continuation token provided is incorrect", "continuation-token", value);
  }
}

const visible = (bucket) => (k) => {
  const rec = bucket.objects.get(k);
  return Boolean(rec) && !rec.versions[0].dm;
};

const FIELD_KEYS = ["type", "meta", "headers", "class", "tags", "acl", "sse", "redirect", "owner"];

const pick = (src, keys) => {
  const out = {};
  for (const k of keys) if (own(src, k)) out[k] = src[k];
  return out;
};

module.exports = {
  abortUpload, deleteObject, removeVersion, newVersion, createBucket, deleteBucket, findVersion, putVersion,
  parseTagging, validateTags, tagsFromXml, tagsXml, objectFields, defaultEncryption, sseHeaders, objectHeaders,
  checkConditions, parseRange, readSource, copyFile, listKeys, tokenEncode, tokenDecode, visible, FIELD_KEYS, pick,
};
