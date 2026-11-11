"use strict";
// ACLs, block public access, ownership controls, authentication and the access decision of every S3 request.

const { asciiStrip, g, isDict, own, truthy } = require("./py");
const { S3Error, denied, invalid, malformed } = require("./errors");
const { ALL_USERS, AUTH, AUTH_USERS, CANNED, LOG_DELIVERY, OWNER_ID, OWNER_NAME } = require("./config");
const { doc, ownerXml, parseXml, text, x } = require("./util");
const { configsOf } = require("./store");
const { Auth, verifyV2, verifyV4 } = require("./sigv4");
const { policyDecision, policyIsPublic } = require("./policy");

function aclFromCanned(canned) {
  const grants = [{ type: "CanonicalUser", id: OWNER_ID, permission: "FULL_CONTROL" }];
  if (canned === "public-read" || canned === "public-read-write") grants.push({ type: "Group", uri: ALL_USERS, permission: "READ" });
  if (canned === "public-read-write") grants.push({ type: "Group", uri: ALL_USERS, permission: "WRITE" });
  if (canned === "authenticated-read") grants.push({ type: "Group", uri: AUTH_USERS, permission: "READ" });
  if (canned === "log-delivery-write") {
    grants.push({ type: "Group", uri: LOG_DELIVERY, permission: "WRITE" }, { type: "Group", uri: LOG_DELIVERY, permission: "READ_ACP" });
  }
  return grants;
}

function aclGrants(acl) {
  if (isDict(acl) && Array.isArray(acl.grants)) return acl.grants;
  return aclFromCanned(isDict(acl) ? g(acl, "canned", "private") : "private");
}

function aclXml(acl) {
  const xsi = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"';
  const inner = aclGrants(acl).map((gr) => {
    let grantee;
    if (gr.type === "Group") {
      grantee = `<Grantee ${xsi} xsi:type="Group">${x("URI", gr.uri)}</Grantee>`;
    } else if (gr.type === "AmazonCustomerByEmail") {
      grantee = `<Grantee ${xsi} xsi:type="AmazonCustomerByEmail">${x("EmailAddress", g(gr, "email", ""))}</Grantee>`;
    } else {
      const name = g(gr, "id") === OWNER_ID ? OWNER_NAME : g(gr, "name", "");
      grantee = `<Grantee ${xsi} xsi:type="CanonicalUser">${x("ID", g(gr, "id", ""))}${name ? x("DisplayName", name) : ""}</Grantee>`;
    }
    return `<Grant>${grantee}${x("Permission", gr.permission)}</Grant>`;
  });
  return doc("AccessControlPolicy", `${ownerXml()}<AccessControlList>${inner.join("")}</AccessControlList>`);
}

const GRANT_HEADERS = {
  "x-amz-grant-read": "READ",
  "x-amz-grant-write": "WRITE",
  "x-amz-grant-read-acp": "READ_ACP",
  "x-amz-grant-write-acp": "WRITE_ACP",
  "x-amz-grant-full-control": "FULL_CONTROL",
};

function aclFromRequest(headers, body, def = null) {
  const canned = headers["x-amz-acl"] || "";
  const grants = [];
  for (const [header, permission] of Object.entries(GRANT_HEADERS)) {
    for (const m of (headers[header] || "").matchAll(/(id|uri|emailAddress)\s*=\s*"?([^",]+)"?/g)) {
      const [, kind, value] = m;
      if (kind === "id") grants.push({ type: "CanonicalUser", id: value, permission });
      else if (kind === "uri") grants.push({ type: "Group", uri: value, permission });
      else grants.push({ type: "AmazonCustomerByEmail", email: value, permission });
    }
  }
  if (canned && grants.length) throw invalid("Specifying both Canned ACLs and Header Grants is not allowed");
  if (canned) {
    if (!CANNED.includes(canned)) throw invalid(`${canned} is not a canned ACL.`, "x-amz-acl", canned);
    return { canned };
  }
  if (grants.length) return { grants };
  if (asciiStrip(body.toString("latin1"))) {
    const root = parseXml(body);
    const found = [];
    for (const grant of root.iter("Grant")) {
      const grantee = grant.find("Grantee");
      const permission = text(grant, "Permission");
      if (!grantee || !["READ", "WRITE", "READ_ACP", "WRITE_ACP", "FULL_CONTROL"].includes(permission)) throw malformed();
      if (text(grantee, "URI")) found.push({ type: "Group", uri: text(grantee, "URI"), permission });
      else if (text(grantee, "EmailAddress")) found.push({ type: "AmazonCustomerByEmail", email: text(grantee, "EmailAddress"), permission });
      else found.push({ type: "CanonicalUser", id: text(grantee, "ID"), name: text(grantee, "DisplayName"), permission });
    }
    return { grants: found };
  }
  return def;
}

function aclPublic(acl, permission) {
  return aclGrants(acl).some((gr) => gr.type === "Group" && [ALL_USERS, AUTH_USERS].includes(g(gr, "uri")) &&
    [permission, "FULL_CONTROL"].includes(gr.permission));
}

function aclCannedName(acl) {
  if (isDict(acl) && truthy(acl.canned)) return String(acl.canned);
  return isDict(acl) && truthy(acl.grants) ? "custom" : "private";
}

const bucketOwnerEnforced = (bucket) => String(g(configsOf(bucket), "ownershipControls", "")).includes("BucketOwnerEnforced");

function publicBlock(bucket) {
  const raw = g(configsOf(bucket), "publicAccessBlock", "");
  const out = { BlockPublicAcls: false, IgnorePublicAcls: false, BlockPublicPolicy: false, RestrictPublicBuckets: false };
  if (raw) {
    let root;
    try {
      root = parseXml(Buffer.from(raw, "utf8"));
    } catch (err) {
      if (err instanceof S3Error) return out;
      throw err;
    }
    for (const name of Object.keys(out)) out[name] = text(root, name).toLowerCase() === "true";
  }
  return out;
}

/** Actions a signed request may always perform, so the owner can repair a policy that locks everyone out. */
const OWNER_ACTIONS = new Set(["s3:GetBucketPolicy", "s3:PutBucketPolicy", "s3:DeleteBucketPolicy"]);
const ACL_READS = ["s3:ListBucket", "s3:ListBucketVersions", "s3:ListBucketMultipartUploads"];
const ACL_WRITES = ["s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"];

/** What the bucket and object ACLs let an anonymous request do when no policy statement allowed it. */
function aclAllows(bucket, action, version, block) {
  if (block.IgnorePublicAcls || bucketOwnerEnforced(bucket)) return false;
  if (ACL_READS.includes(action)) return aclPublic(bucket.meta.acl, "READ");
  if (ACL_WRITES.includes(action)) return aclPublic(bucket.meta.acl, "WRITE");
  if (["s3:GetObject", "s3:GetObjectVersion"].includes(action) && version) return aclPublic(version.acl, "READ");
  return false;
}

/**
 * Whether a request may perform `action` on `bucket` (and the object `key`, whose existing `version` conditions may
 * test). A matching Deny refuses it, signed requests included (but never the bucket policy actions of a signed one);
 * a signed request is otherwise allowed; an anonymous one needs a matching Allow (ignored under RestrictPublicBuckets)
 * or, failing that, an ACL. Without a bucket (account-only operations) only a signed request may.
 */
function allowed(req, bucket, action, key = "", version = null) {
  const signed = req.who !== null;
  if (!bucket) return signed;
  if (signed && OWNER_ACTIONS.has(action)) return true;
  const decision = policyDecision(bucket, req, action, key, version);
  if (decision === "deny") return false;
  if (signed) return true;
  const block = publicBlock(bucket);
  if (decision === "allow" && !block.RestrictPublicBuckets) return true;
  return aclAllows(bucket, action, version, block);
}

/**
 * allowed(), or AccessDenied. With `ownerOnly` (bucket settings, object subresources) only signed requests may, and a
 * bucket policy Deny still applies to them.
 */
function needAuth(req, bucket, action, key = "", version = null, ownerOnly = false) {
  if (ownerOnly && req.who === null) throw denied();
  if (!allowed(req, bucket, action, key, version)) throw denied();
}

// Bucket subresource -> the action name of [GET, PUT, DELETE], as IAM names them.
const CONFIG_ACTIONS = {
  policy: ["GetBucketPolicy", "PutBucketPolicy", "DeleteBucketPolicy"],
  policyStatus: ["GetBucketPolicyStatus", "", ""],
  versioning: ["GetBucketVersioning", "PutBucketVersioning", ""],
  tagging: ["GetBucketTagging", "PutBucketTagging", "PutBucketTagging"],
  cors: ["GetBucketCORS", "PutBucketCORS", "PutBucketCORS"],
  website: ["GetBucketWebsite", "PutBucketWebsite", "DeleteBucketWebsite"],
  lifecycle: ["GetLifecycleConfiguration", "PutLifecycleConfiguration", "PutLifecycleConfiguration"],
  acl: ["GetBucketAcl", "PutBucketAcl", ""],
  publicAccessBlock: ["GetBucketPublicAccessBlock", "PutBucketPublicAccessBlock", "PutBucketPublicAccessBlock"],
  ownershipControls: ["GetBucketOwnershipControls", "PutBucketOwnershipControls", "PutBucketOwnershipControls"],
  "object-lock": ["GetBucketObjectLockConfiguration", "PutBucketObjectLockConfiguration", ""],
  encryption: ["GetEncryptionConfiguration", "PutEncryptionConfiguration", "PutEncryptionConfiguration"],
};
const VERB_INDEX = { GET: 0, HEAD: 0, PUT: 1, DELETE: 2 };
const VERBS = { GET: "Get", HEAD: "Get", DELETE: "Delete" };

/** The IAM action of a bucket configuration request (`s3:Get<Sub>` style for the rarely used ones). */
function configAction(sub, method) {
  const names = own(CONFIG_ACTIONS, sub) ? CONFIG_ACTIONS[sub] : ["", "", ""];
  let name = names[VERB_INDEX[method] ?? 1];
  if (!name) name = `${VERBS[method] || "Put"}Bucket${sub.slice(0, 1).toUpperCase()}${sub.slice(1).replace(/-/g, "")}`;
  return `s3:${name}`;
}

/** The IAM action of an object subresource request (tagging, acl, retention, legal-hold, restore). */
function objectAction(sub, method, versioned) {
  if (sub === "restore") return "s3:RestoreObject";
  const noun = { tagging: "Tagging", acl: "Acl", retention: "Retention", "legal-hold": "LegalHold" }[sub];
  const version = versioned && (sub === "tagging" || sub === "acl") ? "Version" : "";
  return `s3:${VERBS[method] || "Put"}Object${version}${noun}`;
}

/** The console's access summary: "public", "not-public" (all four blocks on) or "objects-can-be-public". */
function bucketAccess(bucket) {
  const block = publicBlock(bucket);
  const aclOpen = aclPublic(bucket.meta.acl, "READ") && !block.IgnorePublicAcls && !bucketOwnerEnforced(bucket);
  if ((policyIsPublic(bucket) && !block.RestrictPublicBuckets) || aclOpen) return "public";
  return Object.values(block).every(Boolean) ? "not-public" : "objects-can-be-public";
}

/** Check the request's signature (header, presigned query, SigV2) and set req.auth; unsigned means anonymous. */
function authenticate(req) {
  if (AUTH === "off") {
    req.auth = new Auth("anonymous", "off");
    if ((req.headers["x-amz-content-sha256"] || "").startsWith("STREAMING-")) req.auth.payload = req.headers["x-amz-content-sha256"];
    return;
  }
  const authorization = req.headers.authorization || "";
  const method = req.method;
  if (authorization.startsWith("AWS4-HMAC-SHA256")) req.auth = verifyV4(method, req.raw_path, req.pairs, req.headers, false);
  else if (authorization.startsWith("AWS ")) req.auth = verifyV2(method, req.raw_path, req.raw_query, req.headers, req.vhost, false);
  else if (req.q["X-Amz-Signature"] !== undefined) req.auth = verifyV4(method, req.raw_path, req.pairs, req.headers, true);
  else if (req.q.Signature !== undefined && req.q.AWSAccessKeyId !== undefined) {
    req.auth = verifyV2(method, req.raw_path, req.raw_query, req.headers, req.vhost, true);
  } else if (authorization) throw new S3Error("InvalidArgument", "Unsupported Authorization Type", 400);
  else req.auth = new Auth(null);
}

module.exports = {
  aclXml, aclFromRequest, aclPublic, aclCannedName, bucketOwnerEnforced, publicBlock, allowed, needAuth, bucketAccess,
  configAction, objectAction,
  authenticate,
};
