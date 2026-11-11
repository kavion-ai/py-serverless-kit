"use strict";
// Bucket requests: create, delete, head, the listings, multi-object delete; settings go to ./config.

const { asciiStrip, bisectLeft, cmpStr, g, pyInt, pyStrip, truthy } = require("../py");
const { S3Error, denied, invalid, malformed } = require("../errors");
const { ARCHIVED, NS, OWNER_ID, OWNER_NAME, REGION } = require("../config");
const { esc, iso, ownerXml, parseXml, text, urlEnc, x } = require("../util");
const { getStore } = require("../store");
const { aclFromRequest, allowed, configAction, needAuth } = require("../access");
const {
  createBucket, deleteBucket, deleteObject, findVersion, listKeys, tokenDecode, tokenEncode, visible,
} = require("../versions");
const { Response, xmlResponse } = require("../http");
const { bucketConfig } = require("./config");

const BUCKET_SUBRESOURCES = ["acl", "cors", "delete", "encryption", "lifecycle", "location", "logging", "notification",
  "policy", "policyStatus", "replication", "requestPayment", "tagging", "uploads", "versioning", "versions", "website",
  "accelerate", "ownershipControls", "publicAccessBlock", "object-lock", "metrics", "analytics", "inventory",
  "intelligent-tiering"];

function maxKeysOf(q, name = "max-keys", def = 1000) {
  let value;
  try {
    value = q[name] !== undefined ? pyInt(q[name]) : def;
  } catch {
    throw invalid("Provided max-keys not an integer or within integer range", name, q[name] || "");
  }
  if (value < 0) throw invalid("Argument maxKeys must be an integer between 0 and 2147483647", name, String(value));
  return Math.min(value, 1000);
}

function contentsXml(bucket, key, version, enc, owner) {
  let out = `<Contents>${x("Key", urlEnc(key, enc))}${x("LastModified", iso(version.time))}${x("ETag", `"${version.etag}"`)}` +
    `${x("Size", version.size)}${x("StorageClass", g(version, "class", "STANDARD"))}`;
  if (truthy(version.checksum)) out += x("ChecksumAlgorithm", version.checksum.alg) + x("ChecksumType", g(version.checksum, "type", "FULL_OBJECT"));
  if (owner) out += ownerXml();
  if (ARCHIVED.includes(version.class) && version.restore) {
    out += `<RestoreStatus><IsRestoreInProgress>false</IsRestoreInProgress>${x("RestoreExpiryDate", iso(version.restore))}</RestoreStatus>`;
  }
  return `${out}</Contents>`;
}

async function bucketRoute(req) {
  const q = req.q;
  const method = req.method;
  const sub = BUCKET_SUBRESOURCES.find((s) => q[s] !== undefined) || "";
  if (method === "PUT" && !sub) return putBucket(req);
  if (method === "POST" && q.delete !== undefined) return deleteObjects(req);
  const bucket = getStore().get(req.bucket);
  if (method === "HEAD" && !sub) {
    needAuth(req, bucket, "s3:ListBucket");
    return new Response(200, Buffer.alloc(0), { "x-amz-bucket-region": bucket.meta.region || REGION, "x-amz-access-point-alias": "false" });
  }
  if (method === "DELETE" && !sub) {
    needAuth(req, bucket, "s3:DeleteBucket", "", null, true);
    deleteBucket(req.bucket);
    return new Response(204);
  }
  if (method === "GET" && !sub) {
    needAuth(req, bucket, "s3:ListBucket");
    return q["list-type"] === "2" ? listObjectsV2(req, bucket) : listObjectsV1(req, bucket);
  }
  if (sub === "versions" && method === "GET") {
    needAuth(req, bucket, "s3:ListBucketVersions");
    return listVersions(req, bucket);
  }
  if (sub === "uploads" && method === "GET") {
    needAuth(req, bucket, "s3:ListBucketMultipartUploads");
    return listUploads(req, bucket);
  }
  if (sub === "location" && method === "GET") {
    needAuth(req, bucket, "s3:GetBucketLocation");
    const region = bucket.meta.region || REGION;
    return new Response(200, `<?xml version="1.0" encoding="UTF-8"?>\n<LocationConstraint xmlns="${NS}">` +
      `${region !== "us-east-1" ? esc(region) : ""}</LocationConstraint>`);
  }
  needAuth(req, bucket, configAction(sub, method), "", null, true);
  return bucketConfig(req, bucket, sub);
}

async function putBucket(req) {
  if (req.who === null) throw denied();
  const body = await req.smallBody();
  let region = REGION;
  if (asciiStrip(body.toString("latin1"))) region = text(parseXml(body), "LocationConstraint") || REGION;
  const acl = aclFromRequest(req.headers, Buffer.alloc(0));
  const ownership = req.headers["x-amz-object-ownership"] || "";
  if (ownership && !["BucketOwnerPreferred", "ObjectWriter", "BucketOwnerEnforced"].includes(ownership)) {
    throw invalid("Invalid x-amz-object-ownership header", "x-amz-object-ownership", ownership);
  }
  if (ownership === "BucketOwnerEnforced" && acl && !["private", "bucket-owner-full-control"].includes(acl.canned)) {
    throw new S3Error("InvalidBucketAclWithObjectOwnership", "Bucket cannot have ACLs set with ObjectOwnership's BucketOwnerEnforced setting");
  }
  const lock = (req.headers["x-amz-bucket-object-lock-enabled"] || "").toLowerCase() === "true";
  createBucket(req.bucket, region, acl, lock, ownership);
  return new Response(200, Buffer.alloc(0), { Location: `/${req.bucket}` });
}

function encodingOf(q) {
  const enc = q["encoding-type"] === "url";
  if (q["encoding-type"] && !enc) throw invalid("Invalid Encoding Method specified in Request", "encoding-type", q["encoding-type"]);
  return enc;
}

const prefixesXml = (prefixes, enc) => prefixes.map((p) => `<CommonPrefixes>${x("Prefix", urlEnc(p, enc))}</CommonPrefixes>`).join("");

function listObjectsV1(req, bucket) {
  const q = req.q;
  const prefix = q.prefix || "";
  const delimiter = q.delimiter || "";
  const marker = q.marker || "";
  const enc = encodingOf(q);
  const maxKeys = maxKeysOf(q);
  const [keys, prefixes, truncated, last] = listKeys(bucket, prefix, delimiter, marker, maxKeys, visible(bucket));
  const items = keys.map((k) => contentsXml(bucket, k, bucket.objects.get(k).versions[0], enc, true)).join("");
  let inner = x("Name", bucket.name) + x("Prefix", urlEnc(prefix, enc)) + x("Marker", urlEnc(marker, enc)) + x("MaxKeys", maxKeys) +
    (delimiter ? x("Delimiter", urlEnc(delimiter, enc)) : "") + x("IsTruncated", truncated ? "true" : "false");
  if (truncated) inner += x("NextMarker", urlEnc(last, enc));
  inner += items + prefixesXml(prefixes, enc);
  if (enc) inner += x("EncodingType", "url");
  return xmlResponse("ListBucketResult", inner);
}

function listObjectsV2(req, bucket) {
  const q = req.q;
  const prefix = q.prefix || "";
  const delimiter = q.delimiter || "";
  const startAfter = q["start-after"] || "";
  const token = q["continuation-token"];
  const enc = encodingOf(q);
  if (token === "") throw invalid("The continuation token provided is incorrect", "continuation-token", "");
  const after = token ? tokenDecode(token) : startAfter;
  const maxKeys = maxKeysOf(q);
  const owner = q["fetch-owner"] === "true";
  const [keys, prefixes, truncated, last] = listKeys(bucket, prefix, delimiter, after, maxKeys, visible(bucket));
  const items = keys.map((k) => contentsXml(bucket, k, bucket.objects.get(k).versions[0], enc, owner)).join("");
  let inner = x("Name", bucket.name) + x("Prefix", urlEnc(prefix, enc)) + x("MaxKeys", maxKeys) +
    (delimiter ? x("Delimiter", urlEnc(delimiter, enc)) : "") + x("IsTruncated", truncated ? "true" : "false") +
    x("KeyCount", keys.length + prefixes.length);
  if (token) inner += x("ContinuationToken", token);
  if (startAfter) inner += x("StartAfter", urlEnc(startAfter, enc));
  if (truncated) inner += x("NextContinuationToken", tokenEncode(last));
  inner += items + prefixesXml(prefixes, enc);
  if (enc) inner += x("EncodingType", "url");
  return xmlResponse("ListBucketResult", inner);
}

function versionEntries(bucket, prefix, delimiter, keyMarker, vidMarker, maxKeys) {
  const keys = bucket.keys();
  let i = bisectLeft(keys, prefix);
  const entries = [];
  const prefixes = [];
  let nextKey = "";
  let nextVid = "";
  let count = 0;
  if (keyMarker) i = Math.max(i, bisectLeft(keys, keyMarker));
  while (i < keys.length) {
    const key = keys[i];
    if (!key.startsWith(prefix)) break;
    if (delimiter) {
      const pos = key.indexOf(delimiter, prefix.length);
      if (pos >= 0) {
        const common = key.slice(0, pos + delimiter.length);
        if (keyMarker && (cmpStr(common, keyMarker) <= 0 || keyMarker.startsWith(common))) {
          i += 1;
          continue;
        }
        if (count >= maxKeys) return [entries, prefixes, true, nextKey, nextVid];
        prefixes.push(common);
        count += 1;
        nextKey = common;
        nextVid = "";
        while (i < keys.length && keys[i].startsWith(common)) i += 1;
        continue;
      }
    }
    const versions = bucket.objects.get(key).versions;
    let start = 0;
    if (keyMarker && key === keyMarker) {
      if (!vidMarker) {
        i += 1;
        continue;
      }
      const ids = versions.map((v) => v.id);
      start = ids.includes(vidMarker) ? ids.indexOf(vidMarker) + 1 : ids.length;
    }
    for (let idx = start; idx < versions.length; idx++) {
      if (count >= maxKeys) return [entries, prefixes, true, nextKey, nextVid];
      entries.push([key, versions[idx], idx === 0]);
      count += 1;
      nextKey = key;
      nextVid = versions[idx].id;
    }
    i += 1;
  }
  return [entries, prefixes, false, "", ""];
}

function checksumListXml(version) {
  if (!truthy(version.checksum)) return "";
  return x("ChecksumAlgorithm", version.checksum.alg) + x("ChecksumType", g(version.checksum, "type", "FULL_OBJECT"));
}

function listVersions(req, bucket) {
  const q = req.q;
  const prefix = q.prefix || "";
  const delimiter = q.delimiter || "";
  const keyMarker = q["key-marker"] || "";
  const vidMarker = q["version-id-marker"] || "";
  if (vidMarker && !keyMarker) throw invalid("A version-id marker cannot be specified without a key marker.", "version-id-marker", vidMarker);
  const enc = q["encoding-type"] === "url";
  const maxKeys = maxKeysOf(q);
  const [entries, prefixes, truncated, nextKey, nextVid] = versionEntries(bucket, prefix, delimiter, keyMarker, vidMarker, maxKeys);
  const items = entries.map(([key, version, latest]) => {
    const common = x("Key", urlEnc(key, enc)) + x("VersionId", version.id) + x("IsLatest", latest ? "true" : "false") +
      x("LastModified", iso(version.time));
    if (version.dm) return `<DeleteMarker>${common}${ownerXml()}</DeleteMarker>`;
    return `<Version>${common}${x("ETag", `"${version.etag}"`)}${x("Size", version.size)}` +
      `${x("StorageClass", g(version, "class", "STANDARD"))}${checksumListXml(version)}${ownerXml()}</Version>`;
  });
  let inner = x("Name", bucket.name) + x("Prefix", urlEnc(prefix, enc)) + x("KeyMarker", urlEnc(keyMarker, enc)) +
    x("VersionIdMarker", vidMarker) + x("MaxKeys", maxKeys) + (delimiter ? x("Delimiter", urlEnc(delimiter, enc)) : "") +
    x("IsTruncated", truncated ? "true" : "false");
  if (truncated) {
    inner += x("NextKeyMarker", urlEnc(nextKey, enc));
    if (nextVid) inner += x("NextVersionIdMarker", nextVid);
  }
  inner += items.join("") + prefixesXml(prefixes, enc);
  if (enc) inner += x("EncodingType", "url");
  return xmlResponse("ListVersionsResult", inner);
}

function listUploads(req, bucket) {
  const q = req.q;
  const prefix = q.prefix || "";
  const delimiter = q.delimiter || "";
  const keyMarker = q["key-marker"] || "";
  const idMarker = q["upload-id-marker"] || "";
  const maxUploads = maxKeysOf(q, "max-uploads");
  const enc = q["encoding-type"] === "url";
  const ups = [...bucket.uploads.values()].sort((a, b) => cmpStr(a.key, b.key) || a.initiated - b.initiated || cmpStr(a.id, b.id));
  const items = [];
  const prefixes = [];
  let truncated = false;
  let nextKey = "";
  let nextId = "";
  for (const up of ups) {
    const key = up.key;
    if (!key.startsWith(prefix)) continue;
    if (keyMarker && (cmpStr(key, keyMarker) < 0 || (key === keyMarker && (!idMarker || cmpStr(up.id, idMarker) <= 0)))) continue;
    if (delimiter) {
      const pos = key.indexOf(delimiter, prefix.length);
      if (pos >= 0) {
        const common = key.slice(0, pos + delimiter.length);
        if (prefixes.includes(common)) continue;
        if (items.length + prefixes.length >= maxUploads) {
          truncated = true;
          break;
        }
        prefixes.push(common);
        continue;
      }
    }
    if (items.length + prefixes.length >= maxUploads) {
      truncated = true;
      break;
    }
    items.push(`<Upload>${x("Key", urlEnc(key, enc))}${x("UploadId", up.id)}` +
      `<Initiator>${x("ID", OWNER_ID)}${x("DisplayName", OWNER_NAME)}</Initiator>${ownerXml()}` +
      `${x("StorageClass", g(up.fields, "class", "STANDARD"))}${x("Initiated", iso(up.initiated))}` +
      (up.alg ? x("ChecksumAlgorithm", up.alg) + x("ChecksumType", g(up, "ctype", "COMPOSITE")) : "") +
      "</Upload>");
    nextKey = key;
    nextId = up.id;
  }
  let inner = x("Bucket", bucket.name) + x("KeyMarker", urlEnc(keyMarker, enc)) + x("UploadIdMarker", idMarker) +
    x("NextKeyMarker", truncated ? urlEnc(nextKey, enc) : "") + x("NextUploadIdMarker", truncated ? nextId : "") +
    x("Prefix", urlEnc(prefix, enc)) + (delimiter ? x("Delimiter", urlEnc(delimiter, enc)) : "") + x("MaxUploads", maxUploads) +
    x("IsTruncated", truncated ? "true" : "false") + items.join("") + prefixesXml(prefixes, enc);
  if (enc) inner += x("EncodingType", "url");
  return xmlResponse("ListMultipartUploadsResult", inner);
}

async function deleteObjects(req) {
  const bucket = getStore().get(req.bucket);
  const root = parseXml(await req.smallBody());
  if (root.tag !== "Delete") throw malformed();
  const quiet = text(root, "Quiet").toLowerCase() === "true";
  const objects = root.findall("Object");
  if (objects.length > 1000) throw malformed();
  const bypass = (req.headers["x-amz-bypass-governance-retention"] || "").toLowerCase() === "true";
  const out = [];
  for (const obj of objects) {
    const key = text(obj, "Key");
    const vidEl = obj.find("VersionId");
    const versionId = vidEl ? pyStrip(vidEl.text || "") : null;
    try {
      if (!allowed(req, bucket, "s3:DeleteObject", key)) throw denied();
      if (vidEl && !versionId) throw new S3Error("NoSuchVersion", "The specified version does not exist.", 404);
      const etag = text(obj, "ETag");
      if (etag) {
        const current = findVersion(bucket, key, versionId);
        if (etag.replace(/^"+|"+$/g, "") !== current.etag) {
          throw new S3Error("PreconditionFailed", "At least one of the pre-conditions you specified did not hold", 412);
        }
      }
      const result = deleteObject(bucket, key, versionId, bypass);
      if (!quiet) {
        let item = x("Key", key);
        if (versionId) item += x("VersionId", versionId);
        if (result.marker) item += x("DeleteMarker", "true") + x("DeleteMarkerVersionId", versionId ? versionId : result.id);
        out.push(`<Deleted>${item}</Deleted>`);
      }
    } catch (err) {
      if (!(err instanceof S3Error)) throw err;
      out.push(`<Error>${x("Key", key)}${versionId ? x("VersionId", versionId) : ""}${x("Code", err.code)}${x("Message", err.message)}</Error>`);
    }
  }
  return xmlResponse("DeleteResult", out.join(""));
}

module.exports = { bucketRoute };
