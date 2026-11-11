"use strict";
// The console's operations (/ui/api/<Operation>), uploads and downloads. They act as the account owner: bucket
// policies are not evaluated for them.

const fs = require("fs");

const { cmpStr, g, isDict, nullObj, own, pget, pyInt, pyLen, pyStr, truthy } = require("../py");
const { S3Error, denied, invalid, noKey } = require("../errors");
const {
  ACCOUNT, ARCHIVED, CANNED, CREDENTIALS, DOMAINS, OWNER_ID, REGION, STD_HEADERS, STORAGE_CLASSES,
} = require("../config");
const { epoch, iso, log, parseTime, parseXml, quote, stripDecl, text } = require("../util");
const { md5Hex } = require("../checksums");
const { configsOf, getStore, unlink } = require("../store");
const { Auth, Received, presign } = require("../sigv4");
const { policyIsPublic } = require("../policy");
const { aclCannedName, aclPublic, bucketAccess, bucketOwnerEnforced, publicBlock } = require("../access");
const { sweepLifecycle } = require("../lifecycle");
const { checkUnlocked, lockConfig } = require("../objectlock");
const {
  FIELD_KEYS, abortUpload, copyFile, createBucket, defaultEncryption, deleteBucket, deleteObject, findVersion,
  listKeys, newVersion, objectFields, pick, putVersion, removeVersion, validateTags, visible,
} = require("../versions");
const { Response, jsonResponse } = require("../http");
const { CONFIGS, setConfig, setPolicy } = require("../routes/config");

/** A required (or optional) console parameter as a string. */
function param(p, name, required = true) {
  const value = pget(p, name);
  if (value === undefined || value === null || value === "") {
    if (required) throw invalid(`${name} is required.`, name, "");
    return "";
  }
  return pyStr(value);
}

/** `p.get(name) or None`: the version id a console call names, or null. */
const optVid = (p) => (truthy(pget(p, "versionId")) ? pget(p, "versionId") : null);

function versionJson(key, version, latest = false) {
  const out = { key, versionId: version.id, modified: iso(version.time), latest, deleteMarker: truthy(version.dm) };
  if (!version.dm) Object.assign(out, { size: version.size, etag: version.etag, class: g(version, "class", "STANDARD"), type: g(version, "type", "") });
  return out;
}

function uiListBuckets() {
  const out = [...getStore().buckets.keys()].sort(cmpStr).map((name) => {
    const b = getStore().buckets.get(name);
    let objects = 0;
    for (const r of b.objects.values()) if (!r.versions[0].dm) objects += 1;
    return {
      name,
      created: iso(b.meta.created),
      region: b.meta.region || REGION,
      versioning: b.meta.versioning || "",
      objectLock: truthy(b.meta.object_lock),
      objects,
      public: policyIsPublic(b) || aclPublic(b.meta.acl, "READ"),
      access: bucketAccess(b),
      publicBlock: publicBlock(b),
    };
  });
  return { buckets: out };
}

function uiCreateBucket(p) {
  const name = param(p, "bucket");
  const bucket = createBucket(name, pyStr(pget(p, "region") || REGION), null, truthy(pget(p, "objectLock")));
  if (truthy(pget(p, "versioning")) && !bucket.meta.versioning) {
    bucket.meta.versioning = "Enabled";
    bucket.saveMeta();
  }
  return { bucket: name };
}

function uiDeleteBucket(p) {
  const name = param(p, "bucket");
  const bucket = getStore().get(name);
  if (truthy(pget(p, "force"))) {
    for (const key of [...bucket.objects.keys()]) {
      const rec = bucket.objects.get(key);
      for (const version of rec ? [...rec.versions] : []) {
        if (!version.dm) checkUnlocked(version, truthy(pget(p, "bypass")));
        removeVersion(bucket, key, version.id);
      }
    }
  }
  deleteBucket(name);
  return { deleted: name };
}

/** The bucket's ObjectOwnership setting, or "" when it has none. */
function ownershipOf(bucket) {
  const raw = g(configsOf(bucket), "ownershipControls", "");
  if (!raw) return "";
  try {
    return text(parseXml(Buffer.from(raw, "utf8")), "Rule/ObjectOwnership");
  } catch (err) {
    if (err instanceof S3Error) return "";
    throw err;
  }
}

function uiBucketInfo(p) {
  const bucket = getStore().get(param(p, "bucket"));
  let size = 0;
  let versions = 0;
  let objects = 0;
  for (const rec of bucket.objects.values()) {
    if (!rec.versions[0].dm) objects += 1;
    for (const v of rec.versions) {
      versions += 1;
      size += pyInt(v.size || 0);
    }
  }
  const meta = bucket.meta;
  const configs = {};
  for (const [k, v] of Object.entries(truthy(meta.configs) ? meta.configs : {})) configs[k] = stripDecl(v);
  const ids = {};
  for (const [k, v] of Object.entries(truthy(meta.ids) ? meta.ids : {})) ids[k] = Object.keys(v).sort(cmpStr);
  return {
    name: bucket.name,
    created: iso(meta.created),
    region: meta.region || REGION,
    versioning: meta.versioning || "",
    mfaDelete: meta.mfa_delete || "",
    objectLock: truthy(meta.object_lock),
    tags: truthy(meta.tags) ? meta.tags : {},
    policy: meta.policy || "",
    acl: aclCannedName(meta.acl),
    configs,
    ids,
    publicBlock: publicBlock(bucket),
    policyPublic: policyIsPublic(bucket),
    stats: { objects, versions, bytes: size, uploads: bucket.uploads.size },
    websiteUrl: `/-/website/${bucket.name}/`,
    websiteHosts: DOMAINS.map((d) => `${bucket.name}.s3-website.${d}`),
    access: bucketAccess(bucket),
    arn: `arn:aws:s3:::${bucket.name}`,
    ownership: ownershipOf(bucket),
    account: ACCOUNT,
  };
}

function uiListObjects(p) {
  const bucket = getStore().get(param(p, "bucket"));
  const prefix = pyStr(pget(p, "prefix") || "");
  const search = pyStr(pget(p, "search") || "").toLowerCase();
  const delimiter = search ? "" : pyStr(pget(p, "delimiter", "/"));
  const after = pyStr(pget(p, "token") || "");
  const limit = Math.min(pyInt(pget(p, "max") || 500), 1000);
  let include = visible(bucket);
  if (truthy(pget(p, "deleted"))) include = (k) => Boolean(bucket.objects.get(k));
  if (search) {
    const base = include;
    include = (k) => base(k) && k.slice(prefix.length).toLowerCase().includes(search);
  }
  const [keys, prefixes, truncated, last] = listKeys(bucket, prefix, delimiter, after, limit, include);
  const objects = keys.map((k) => versionJson(k, bucket.objects.get(k).versions[0], true));
  return { folders: prefixes, objects, next: truncated ? last : "" };
}

function uiHeadObject(p) {
  const bucket = getStore().get(param(p, "bucket"));
  const key = param(p, "key");
  let rec = bucket.objects.get(key);
  let version;
  if (!truthy(pget(p, "versionId")) && rec && rec.versions[0].dm) {
    // A deleted object (shown with "Show deleted"): its newest real version.
    const live = rec.versions.filter((v) => !v.dm);
    if (!live.length) throw noKey(key);
    version = live[0];
  } else {
    version = findVersion(bucket, key, optVid(p));
    rec = bucket.objects.get(key);
  }
  const out = versionJson(key, version, version === rec.versions[0]);
  Object.assign(out, {
    meta: truthy(version.meta) ? version.meta : {},
    headers: truthy(version.headers) ? version.headers : {},
    tags: truthy(version.tags) ? version.tags : {},
    acl: aclCannedName(version.acl),
    checksum: g(version, "checksum", null),
    parts: truthy(version.parts) ? version.parts.length : 0,
    retention: truthy(version.retention) ? { mode: version.retention.mode, until: iso(version.retention.until) } : null,
    legalHold: truthy(version.hold),
    sse: truthy(version.sse) ? version.sse : {},
    redirect: version.redirect || "",
    objectLock: lockConfig(bucket).enabled,
    versions: rec.versions.map((v, i) => versionJson(key, v, i === 0)),
    restore: version.restore ? iso(version.restore) : "",
  });
  return out;
}

/** Every version and delete marker under `prefix` (at most 2000); with a delimiter, only the keys directly under it. */
function uiListVersions(p) {
  const bucket = getStore().get(param(p, "bucket"));
  const prefix = pyStr(pget(p, "prefix") || "");
  const delimiter = pyStr(pget(p, "delimiter") || "");
  const out = [];
  const folders = [];
  for (const key of bucket.keys()) {
    if (!key.startsWith(prefix)) continue;
    const pos = delimiter ? key.indexOf(delimiter, prefix.length) : -1;
    if (pos >= 0) {
      // Keys are sorted, so the keys of one folder come together.
      const folder = key.slice(0, pos + delimiter.length);
      if (folders[folders.length - 1] !== folder) folders.push(folder);
      continue;
    }
    const versions = bucket.objects.get(key).versions;
    for (let i = 0; i < versions.length; i++) {
      out.push(versionJson(key, versions[i], i === 0));
      if (out.length >= 2000) return { versions: out, folders, truncated: true };
    }
  }
  return { versions: out, folders, truncated: false };
}

function uiDeleteObjects(p) {
  const deleted = [];
  const errors = [];
  const bucket = getStore().get(param(p, "bucket"));
  const items = pget(p, "objects");
  for (const item of truthy(items) ? items : []) {
    const key = pyStr(pget(item, "key") || "");
    const itemVid = truthy(pget(item, "versionId")) ? pget(item, "versionId") : null;
    try {
      if (key.endsWith("/") && truthy(pget(item, "recursive"))) {
        for (const sub of bucket.keys().filter((k) => k.startsWith(key))) deleteObject(bucket, sub, null, false);
      } else {
        deleteObject(bucket, key, itemVid, truthy(pget(p, "bypass")));
      }
      deleted.push(key);
    } catch (err) {
      if (!(err instanceof S3Error)) throw err;
      errors.push({ key, code: err.code, message: err.message });
    }
  }
  return { deleted, errors };
}

async function uiCopy(p) {
  const srcBucket = param(p, "bucket");
  const srcKey = param(p, "key");
  const dstBucket = pyStr(pget(p, "toBucket") || srcBucket);
  const dstKey = param(p, "toKey");
  const moved = [];
  const sb = getStore().get(srcBucket);
  const db = getStore().get(dstBucket);
  let pairs;
  if (srcKey.endsWith("/")) {
    pairs = sb.keys().filter((k) => k.startsWith(srcKey) && !sb.objects.get(k).versions[0].dm)
      .map((k) => [k, `${dstKey.replace(/\/+$/, "")}/${k.slice(srcKey.length)}`]);
  } else {
    pairs = [[srcKey, dstKey]];
  }
  for (const [skey, dkey] of pairs) {
    if (sb === db && skey === dkey) continue;
    const src = { ...findVersion(sb, skey, pairs.length === 1 ? optVid(p) : null) };
    const received = await copyFile(sb.blobPath(src.blob), 0, pyInt(src.size) - 1, truthy(src.checksum) ? g(src.checksum, "alg", "") : "");
    const blob = getStore().commitBlob(db, received.path);
    putVersion(db, dkey, newVersion(received, pick(src, FIELD_KEYS), blob));
    if (truthy(pget(p, "move"))) deleteObject(sb, skey, null, false);
    moved.push(dkey);
  }
  return { copied: moved };
}

function uiCreateFolder(p) {
  let key = param(p, "key");
  if (!key.endsWith("/")) key += "/";
  const bucket = getStore().get(param(p, "bucket"));
  const tmp = getStore().tempFile();
  fs.writeFileSync(tmp, Buffer.alloc(0));
  const received = new Received();
  received.path = tmp;
  received.md5 = md5Hex(Buffer.alloc(0));
  const blob = getStore().commitBlob(bucket, tmp);
  putVersion(bucket, key, newVersion(received, {
    type: "application/x-directory",
    meta: {},
    headers: {},
    class: "STANDARD",
    tags: {},
    owner: OWNER_ID,
    sse: defaultEncryption(bucket),
  }, blob));
  return { key };
}

function stringMap(value) {
  const out = {};
  for (const [k, v] of Object.entries(truthy(value) ? value : {})) out[pyStr(k)] = pyStr(v);
  return out;
}

function uiPutObjectTags(p) {
  const tags = stringMap(pget(p, "tags"));
  validateTags(tags);
  const bucket = getStore().get(param(p, "bucket"));
  const version = findVersion(bucket, param(p, "key"), optVid(p));
  version.tags = tags;
  bucket.saveRecord(param(p, "key"));
  return { tags };
}

/** Replace the content type, standard headers, user metadata and storage class (a copy onto itself). */
async function uiUpdateMeta(p) {
  const bucket = getStore().get(param(p, "bucket"));
  const key = param(p, "key");
  const src = { ...findVersion(bucket, key, null) };
  const file = bucket.blobPath(src.blob);
  const headers = {};
  for (const [k, v] of Object.entries(truthy(pget(p, "headers")) ? pget(p, "headers") : {})) {
    if (STD_HEADERS.includes(k.toLowerCase()) && truthy(v)) headers[k.toLowerCase()] = pyStr(v);
  }
  const meta = {};
  for (const [k, v] of Object.entries(truthy(pget(p, "meta")) ? pget(p, "meta") : {})) if (k) meta[pyStr(k).toLowerCase()] = pyStr(v);
  if (Object.entries(meta).reduce((n, [k, v]) => n + pyLen(k) + pyLen(v), 0) > 2048) {
    throw new S3Error("MetadataTooLarge", "Your metadata headers exceed the maximum allowed metadata size.");
  }
  const sclass = pyStr(pget(p, "class") || src.class || "STANDARD");
  if (!STORAGE_CLASSES.includes(sclass)) throw new S3Error("InvalidStorageClass", "The storage class you specified is not valid");
  const received = await copyFile(file, 0, pyInt(src.size) - 1, truthy(src.checksum) ? g(src.checksum, "alg", "") : "");
  const fields = pick(src, ["tags", "acl", "sse", "redirect", "owner", "retention", "hold"]);
  Object.assign(fields, { type: pyStr(pget(p, "type") || src.type || "binary/octet-stream"), headers, meta, class: sclass });
  const blob = getStore().commitBlob(bucket, received.path);
  const version = putVersion(bucket, key, newVersion(received, fields, blob));
  return { versionId: version.id };
}

/** Make an older version the current one (copies it on top, like the AWS console). */
async function uiRestoreVersion(p) {
  const bucket = getStore().get(param(p, "bucket"));
  const key = param(p, "key");
  const src = { ...findVersion(bucket, key, param(p, "versionId")) };
  const received = await copyFile(bucket.blobPath(src.blob), 0, pyInt(src.size) - 1, truthy(src.checksum) ? g(src.checksum, "alg", "") : "");
  const blob = getStore().commitBlob(bucket, received.path);
  const version = putVersion(bucket, key, newVersion(received, pick(src, FIELD_KEYS), blob));
  return { versionId: version.id };
}

/** One bucket setting: versioning, tags, policy, acl, or a configuration document (XML, "" deletes it). */
function uiPutBucketSetting(p, req) {
  const name = param(p, "bucket");
  const setting = param(p, "setting");
  const value = pget(p, "value");
  const bucket = getStore().get(name);
  if (setting === "versioning") {
    if (value !== "Enabled" && value !== "Suspended") throw invalid("versioning must be Enabled or Suspended");
    if (truthy(bucket.meta.object_lock) && value === "Suspended") {
      throw new S3Error("InvalidBucketState", "Object Lock is on: versioning cannot be suspended.", 409);
    }
    bucket.meta.versioning = value;
    bucket.saveMeta();
  } else if (setting === "tags") {
    const tags = stringMap(value);
    validateTags(tags, 50);
    bucket.meta.tags = tags;
    bucket.saveMeta();
  } else if (setting === "policy") {
    if (truthy(value)) {
      setPolicy(bucket, pyStr(value));
    } else {
      bucket.meta.policy = null;
      bucket.saveMeta();
    }
  } else if (setting === "acl") {
    if (!CANNED.includes(value)) throw invalid("Unknown canned ACL");
    if (bucketOwnerEnforced(bucket) && !["private", "bucket-owner-full-control"].includes(value)) {
      throw new S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs (ownership controls are BucketOwnerEnforced).");
    }
    if (publicBlock(bucket).BlockPublicAcls && ["public-read", "public-read-write"].includes(value)) {
      throw denied("Block public access is on (BlockPublicAcls).");
    }
    bucket.meta.acl = { canned: value };
    bucket.saveMeta();
  } else if (own(CONFIGS, setting)) {
    if (truthy(value)) {
      setConfig(bucket, setting, Buffer.from(pyStr(value), "utf8"));
    } else {
      if (setting === "object-lock") throw invalid("Object Lock cannot be turned off.");
      if (!isDict(bucket.meta.configs)) bucket.meta.configs = {};
      delete bucket.meta.configs[setting];
      bucket.saveMeta();
    }
  } else {
    throw invalid(`Unknown setting ${setting}.`);
  }
  return uiBucketInfo({ bucket: name }, req);
}

function uiPutObjectAcl(p) {
  const value = param(p, "acl");
  if (!CANNED.includes(value)) throw invalid("Unknown canned ACL");
  const bucket = getStore().get(param(p, "bucket"));
  if (bucketOwnerEnforced(bucket) && !["private", "bucket-owner-full-control"].includes(value)) {
    throw new S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs.");
  }
  if (publicBlock(bucket).BlockPublicAcls && ["public-read", "public-read-write"].includes(value)) {
    throw denied("Block public access is on (BlockPublicAcls).");
  }
  const version = findVersion(bucket, param(p, "key"), optVid(p));
  version.acl = { canned: value };
  bucket.saveRecord(param(p, "key"));
  return { acl: value };
}

function uiObjectLock(p, req) {
  const bucket = getStore().get(param(p, "bucket"));
  if (!lockConfig(bucket).enabled) throw new S3Error("InvalidRequest", "Bucket is missing Object Lock Configuration");
  const key = param(p, "key");
  const version = findVersion(bucket, key, optVid(p));
  if (own(p, "legalHold")) version.hold = truthy(p.legalHold);
  if (own(p, "mode")) {
    const mode = pyStr(pget(p, "mode") || "");
    const old = truthy(version.retention) ? version.retention : {};
    const until = parseTime(pyStr(pget(p, "until") || ""));
    if (g(old, "until", 0) > epoch()) {
      const shorter = !mode || (until || 0) < old.until;
      if (shorter && (old.mode === "COMPLIANCE" || !truthy(pget(p, "bypass")))) {
        throw denied("The object is protected by its retention; it cannot be shortened.");
      }
    }
    if (mode) {
      if (!["GOVERNANCE", "COMPLIANCE"].includes(mode) || until === null || until <= epoch()) {
        throw invalid("Pick GOVERNANCE or COMPLIANCE and a date in the future.");
      }
      version.retention = { mode, until };
    } else {
      delete version.retention;
    }
  }
  bucket.saveRecord(key);
  return uiHeadObject(p, req);
}

/** A presigned GET or PUT URL; a GET with `disposition` opens inline or downloads, like the AWS console. */
function uiPresign(p, req) {
  let expires;
  try {
    expires = pyInt(pget(p, "expires") || 3600);
  } catch {
    throw invalid("Expiry must be a number of seconds.");
  }
  if (expires < 1 || expires > 604800) throw invalid("Expiry must be between 1 second and 7 days.");
  const access = CREDENTIALS.has(req.who) ? req.who : CREDENTIALS.keys().next().value || "";
  if (!access) throw invalid("Share links need a credential (S3_SECRET_ACCESS_KEY); authentication is off.");
  const method = pyStr(pget(p, "method") || "GET").toUpperCase();
  if (method !== "GET" && method !== "PUT") throw invalid("method must be GET or PUT");
  const host = pyStr(pget(p, "host") || req.host);
  const scheme = pyStr(pget(p, "scheme") || "") === "https" ? "https" : "http";
  const key = param(p, "key");
  const extra = [];
  const versionId = pyStr(pget(p, "versionId") || "");
  if (versionId) extra.push(["versionId", versionId]);
  // Signed like any other parameter: changing it breaks the link.
  if (method === "GET" && truthy(pget(p, "disposition"))) {
    extra.push(["response-content-disposition", dispositionOf(p, key)]);
  }
  return { url: presign(method, host, param(p, "bucket"), key, expires, access, scheme, extra), expires };
}

/** `inline`, or `attachment` with the file name (by default the key's last segment). */
function dispositionOf(p, key) {
  const disposition = pyStr(pget(p, "disposition"));
  if (disposition !== "inline" && disposition !== "attachment") {
    throw invalid("disposition must be inline or attachment", "disposition", disposition);
  }
  if (disposition === "inline") return disposition;
  const name = pyStr(pget(p, "filename") || "") || key.replace(/\/+$/, "").split("/").pop() || "download";
  return `attachment; filename*=UTF-8''${quote(name, "")}`;
}

/** Remove every version and delete marker and abort every unfinished upload; locked versions stay and are reported. */
function uiEmptyBucket(p) {
  const bucket = getStore().get(param(p, "bucket"));
  let deleted = 0;
  const errors = [];
  for (const key of [...bucket.keys()]) {
    const rec = bucket.objects.get(key);
    for (const version of rec ? [...rec.versions] : []) {
      try {
        deleteObject(bucket, key, version.id, false);
        deleted += 1;
      } catch (err) {
        if (!(err instanceof S3Error)) throw err;
        errors.push({ key, versionId: version.id, code: err.code, message: err.message });
      }
    }
  }
  for (const uploadId of [...bucket.uploads.keys()]) abortUpload(bucket, uploadId);
  return { deleted, errors };
}

function uiListUploads(p) {
  const bucket = getStore().get(param(p, "bucket"));
  return {
    uploads: [...bucket.uploads.values()].sort((a, b) => a.initiated - b.initiated).map((u) => ({
      key: u.key,
      uploadId: u.id,
      initiated: iso(u.initiated),
      parts: u.parts.size,
      bytes: [...u.parts.values()].reduce((t, part) => t + pyInt(part.size), 0),
    })),
  };
}

function uiAbortUpload(p) {
  const bucket = getStore().get(param(p, "bucket"));
  if (!bucket.uploads.has(param(p, "uploadId"))) throw new S3Error("NoSuchUpload", "The specified upload does not exist.", 404);
  abortUpload(bucket, param(p, "uploadId"));
  return { aborted: true };
}

function uiRestoreArchived(p) {
  const days = pyInt(pget(p, "days") || 1);
  const bucket = getStore().get(param(p, "bucket"));
  const version = findVersion(bucket, param(p, "key"), optVid(p));
  if (!ARCHIVED.includes(version.class)) throw new S3Error("InvalidObjectState", "Only GLACIER and DEEP_ARCHIVE objects are restored.", 403);
  version.restore = epoch() + days * 86400;
  bucket.saveRecord(param(p, "key"));
  return { restored: true };
}

const uiRunLifecycle = () => ({ changes: sweepLifecycle() });

const UI_OPS = {
  ListBuckets: uiListBuckets,
  CreateBucket: uiCreateBucket,
  DeleteBucket: uiDeleteBucket,
  EmptyBucket: uiEmptyBucket,
  BucketInfo: uiBucketInfo,
  ListObjects: uiListObjects,
  HeadObject: uiHeadObject,
  ListVersions: uiListVersions,
  DeleteObjects: uiDeleteObjects,
  Copy: uiCopy,
  CreateFolder: uiCreateFolder,
  PutObjectTags: uiPutObjectTags,
  UpdateMeta: uiUpdateMeta,
  RestoreVersion: uiRestoreVersion,
  PutBucketSetting: uiPutBucketSetting,
  PutObjectAcl: uiPutObjectAcl,
  ObjectLock: uiObjectLock,
  Presign: uiPresign,
  ListUploads: uiListUploads,
  AbortUpload: uiAbortUpload,
  RestoreArchived: uiRestoreArchived,
  RunLifecycle: uiRunLifecycle,
};

async function uiUpload(req) {
  const bucketName = req.q.bucket || "";
  const key = req.q.key || "";
  if (!key) throw invalid("key is required", "key", "");
  const bucket = getStore().get(bucketName);
  const headers = nullObj();
  headers["content-type"] = req.headers["content-type"] || "binary/octet-stream";
  if (req.q.class) headers["x-amz-storage-class"] = req.q.class;
  const fields = objectFields(headers, bucket);
  req.auth = new Auth("console", "console");
  req.auth.payload = "UNSIGNED-PAYLOAD";
  const received = await req.payload("", "");
  let version;
  try {
    const blob = getStore().commitBlob(bucket, received.path);
    received.path = null;
    version = putVersion(bucket, key, newVersion(received, fields, blob));
  } finally {
    if (received.path) unlink(received.path);
  }
  log("console upload", bucketName, key, received.size, "bytes");
  return jsonResponse({ key, etag: version.etag, versionId: version.id });
}

function uiDownload(req) {
  const bucket = getStore().get(req.q.bucket || "");
  const key = req.q.key || "";
  const version = { ...findVersion(bucket, key, req.q.versionId || null) };
  const file = bucket.blobPath(version.blob);
  const name = key.replace(/\/+$/, "").split("/").pop() || "download";
  const inline = req.q.inline === "1";
  const ctype = version.type || "binary/octet-stream";
  // Inline previews only for types a browser shows without running anything from the bucket.
  let safeInline = inline && (["image/", "video/", "audio/", "text/plain"].some((t) => ctype.startsWith(t)) || ctype === "application/pdf");
  if (ctype.startsWith("image/svg")) safeInline = false;
  const headers = {
    "Content-Disposition": `${safeInline ? "inline" : "attachment"}; filename*=UTF-8''${quote(name)}`,
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; sandbox",
  };
  return new Response(200, Buffer.alloc(0), headers, safeInline ? ctype : "application/octet-stream", file, 0, pyInt(version.size));
}

module.exports = { UI_OPS, uiUpload, uiDownload };
