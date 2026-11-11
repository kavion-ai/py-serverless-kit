"use strict";
// Bucket settings: versioning, tags, policy, ACL and the configuration documents kept as XML.

const { asList, cmpStr, g, isDict, own, truthy } = require("../py");
const { S3Error, denied, invalid, malformed, notAllowed } = require("../errors");
const { NS } = require("../config");
const { UTF8, UTF8_STRICT, parseXml, stripDecl, text, x } = require("../util");
const { policyIsPublic, statementsPublic } = require("../policy");
const { aclFromRequest, aclPublic, aclXml, bucketOwnerEnforced, publicBlock } = require("../access");
const { validateCors } = require("../cors");
const { parseLifecycle } = require("../lifecycle");
const { tagsFromXml, tagsXml } = require("../versions");
const { Response, xmlResponse } = require("../http");

// Bucket configurations kept as the XML the client sent: subresource -> [error code when missing, its message].
const CONFIGS = {
  cors: ["NoSuchCORSConfiguration", "The CORS configuration does not exist"],
  lifecycle: ["NoSuchLifecycleConfiguration", "The lifecycle configuration does not exist"],
  website: ["NoSuchWebsiteConfiguration", "The specified bucket does not have a website configuration"],
  encryption: ["ServerSideEncryptionConfigurationNotFoundError", "The server side encryption configuration was not found"],
  replication: ["ReplicationConfigurationNotFoundError", "The replication configuration was not found"],
  ownershipControls: ["OwnershipControlsNotFoundError", "The bucket ownership controls were not found"],
  publicAccessBlock: ["NoSuchPublicAccessBlockConfiguration", "The public access block configuration was not found"],
  "object-lock": ["ObjectLockConfigurationNotFoundError", "Object Lock configuration does not exist for this bucket"],
  logging: ["", ""],
  notification: ["", ""],
  accelerate: ["", ""],
  requestPayment: ["", ""],
};

// Defaults returned by GET when a stored-only configuration was never set.
const EMPTY_CONFIGS = {
  logging: `<BucketLoggingStatus xmlns="${NS}"/>`,
  notification: `<NotificationConfiguration xmlns="${NS}"/>`,
  accelerate: `<AccelerateConfiguration xmlns="${NS}"/>`,
  requestPayment: `<RequestPaymentConfiguration xmlns="${NS}"><Payer>BucketOwner</Payer></RequestPaymentConfiguration>`,
};

const ID_CONFIGS = {
  metrics: "MetricsConfiguration",
  analytics: "AnalyticsConfiguration",
  inventory: "InventoryConfiguration",
  "intelligent-tiering": "IntelligentTieringConfiguration",
};

const xmlDoc = (raw) => new Response(200, `<?xml version="1.0" encoding="UTF-8"?>\n${stripDecl(raw)}`);

/** GET / PUT / DELETE of a bucket subresource (versioning, tags, policy, ACL and the configuration documents). */
async function bucketConfig(req, bucket, sub) {
  const method = req.method;
  if (!isDict(bucket.meta.configs)) bucket.meta.configs = {};
  const configs = bucket.meta.configs;
  if (sub === "versioning") {
    if (method === "GET") {
      let inner = "";
      if (bucket.meta.versioning) inner += x("Status", bucket.meta.versioning);
      if (bucket.meta.mfa_delete) inner += x("MfaDelete", bucket.meta.mfa_delete);
      return xmlResponse("VersioningConfiguration", inner);
    }
    if (method === "PUT") {
      const root = parseXml(await req.smallBody());
      const status = text(root, "Status");
      if (!["Enabled", "Suspended", ""].includes(status)) throw malformed();
      if (truthy(bucket.meta.object_lock) && status === "Suspended") {
        throw new S3Error("InvalidBucketState",
          "An Object Lock configuration is present on this bucket, so the versioning state cannot be changed.", 409);
      }
      if (status) bucket.meta.versioning = status;
      if (text(root, "MfaDelete")) bucket.meta.mfa_delete = text(root, "MfaDelete");
      bucket.saveMeta();
      return new Response(200);
    }
  }
  if (sub === "tagging") {
    if (method === "GET") {
      if (!truthy(bucket.meta.tags)) throw new S3Error("NoSuchTagSet", "The TagSet does not exist", 404, { BucketName: bucket.name });
      return new Response(200, tagsXml(bucket.meta.tags));
    }
    if (method === "PUT") {
      const tags = tagsFromXml(await req.smallBody(), 50);
      bucket.meta.tags = tags;
      bucket.saveMeta();
      return new Response(204);
    }
    if (method === "DELETE") {
      bucket.meta.tags = {};
      bucket.saveMeta();
      return new Response(204);
    }
  }
  if (sub === "policy") {
    if (method === "GET") {
      if (!bucket.meta.policy) throw new S3Error("NoSuchBucketPolicy", "The bucket policy does not exist", 404, { BucketName: bucket.name });
      return new Response(200, Buffer.from(bucket.meta.policy, "utf8"), {}, "application/json");
    }
    if (method === "PUT") {
      const raw = UTF8.decode(await req.smallBody(20 * 1024));
      setPolicy(bucket, raw);
      return new Response(204);
    }
    if (method === "DELETE") {
      bucket.meta.policy = null;
      bucket.saveMeta();
      return new Response(204);
    }
  }
  if (sub === "policyStatus" && method === "GET") {
    return xmlResponse("PolicyStatus", x("IsPublic", policyIsPublic(bucket) ? "true" : "false"));
  }
  if (sub === "acl") {
    if (method === "GET") return new Response(200, aclXml(bucket.meta.acl));
    if (method === "PUT") {
      const acl = aclFromRequest(req.headers, await req.smallBody());
      if (!acl) throw malformed();
      if (bucketOwnerEnforced(bucket) && !["private", "bucket-owner-full-control"].includes(acl.canned)) {
        throw new S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs");
      }
      if (publicBlock(bucket).BlockPublicAcls && (aclPublic(acl, "READ") || aclPublic(acl, "WRITE"))) throw denied();
      bucket.meta.acl = acl;
      bucket.saveMeta();
      return new Response(200);
    }
  }
  if (own(ID_CONFIGS, sub)) {
    if (!isDict(bucket.meta.ids)) bucket.meta.ids = {};
    if (!isDict(bucket.meta.ids[sub])) bucket.meta.ids[sub] = {};
    const store = bucket.meta.ids[sub];
    const configId = req.q.id || "";
    const element = ID_CONFIGS[sub];
    if (method === "GET" && !configId) {
      const inner = Object.keys(store).sort(cmpStr).map((k) => stripDecl(store[k])).join("") + x("IsTruncated", "false");
      const root = {
        metrics: "ListMetricsConfigurationsResult",
        analytics: "ListBucketAnalyticsConfigurationResult",
        inventory: "ListInventoryConfigurationsResult",
        "intelligent-tiering": "ListBucketIntelligentTieringConfigurationsOutput",
      }[sub];
      return xmlResponse(root, inner);
    }
    if (!configId) throw invalid("The id parameter is required", "id", "");
    if (method === "GET") {
      if (!own(store, configId)) throw new S3Error("NoSuchConfiguration", "The specified configuration does not exist.", 404);
      return xmlDoc(store[configId]);
    }
    if (method === "PUT") {
      const body = await req.smallBody();
      const root = parseXml(body);
      if (root.tag !== element) throw malformed();
      store[configId] = UTF8_STRICT.decode(body);
      bucket.saveMeta();
      return new Response(sub !== "inventory" ? 204 : 200);
    }
    if (method === "DELETE") {
      delete store[configId];
      bucket.saveMeta();
      return new Response(204);
    }
  }
  if (own(CONFIGS, sub)) {
    const [missingCode, missingMessage] = CONFIGS[sub];
    if (method === "GET") {
      const raw = g(configs, sub);
      if (!raw) {
        if (own(EMPTY_CONFIGS, sub)) return xmlDoc(EMPTY_CONFIGS[sub]);
        if (sub === "encryption") {
          return xmlResponse("ServerSideEncryptionConfiguration",
            `<Rule><ApplyServerSideEncryptionByDefault>${x("SSEAlgorithm", "AES256")}</ApplyServerSideEncryptionByDefault>` +
            "<BucketKeyEnabled>false</BucketKeyEnabled></Rule>");
        }
        throw new S3Error(missingCode, missingMessage, 404, { BucketName: bucket.name });
      }
      return xmlDoc(raw);
    }
    if (method === "PUT") {
      setConfig(bucket, sub, await req.smallBody());
      return new Response(200);
    }
    if (method === "DELETE") {
      if (sub === "object-lock") throw notAllowed();
      delete configs[sub];
      bucket.saveMeta();
      return new Response(204);
    }
  }
  throw new S3Error("NotImplemented", "A header or query you provided implies functionality that is not implemented.", 501);
}

function setPolicy(bucket, raw) {
  let policy;
  try {
    policy = JSON.parse(raw);
  } catch {
    throw new S3Error("MalformedPolicy", "Policies must be valid JSON and the first byte must be '{'");
  }
  if (!isDict(policy) || !(Array.isArray(policy.Statement) || isDict(policy.Statement))) {
    throw new S3Error("MalformedPolicy", "Missing required field Statement");
  }
  for (const st of asList(policy.Statement)) {
    if (!isDict(st) || !["Allow", "Deny"].includes(st.Effect)) throw new S3Error("MalformedPolicy", "Statement must have an Effect of Allow or Deny");
    if (!own(st, "Action") && !own(st, "NotAction")) throw new S3Error("MalformedPolicy", "Missing required field Action");
    for (const resource of asList(g(st, "Resource"))) {
      if (typeof resource === "string" && !resource.startsWith(`arn:aws:s3:::${bucket.name}`)) {
        throw new S3Error("MalformedPolicy", "Policy has invalid resource");
      }
    }
  }
  if (publicBlock(bucket).BlockPublicPolicy && statementsPublic(policy)) throw denied();
  bucket.meta.policy = raw;
  bucket.saveMeta();
}

const CONFIG_ROOTS = {
  cors: "CORSConfiguration",
  lifecycle: "LifecycleConfiguration",
  website: "WebsiteConfiguration",
  encryption: "ServerSideEncryptionConfiguration",
  replication: "ReplicationConfiguration",
  ownershipControls: "OwnershipControls",
  publicAccessBlock: "PublicAccessBlockConfiguration",
  "object-lock": "ObjectLockConfiguration",
  logging: "BucketLoggingStatus",
  notification: "NotificationConfiguration",
  accelerate: "AccelerateConfiguration",
  requestPayment: "RequestPaymentConfiguration",
};

function setConfig(bucket, sub, body) {
  const root = parseXml(body);
  if (root.tag !== CONFIG_ROOTS[sub]) throw malformed();
  if (sub === "cors") {
    validateCors(body);
  } else if (sub === "lifecycle") {
    parseLifecycle(body);
  } else if (sub === "website") {
    if (!root.find("RedirectAllRequestsTo") && !text(root, "IndexDocument/Suffix")) {
      throw invalid("A value for IndexDocument Suffix must be provided if RedirectAllRequestsTo is empty");
    }
  } else if (sub === "replication") {
    if (bucket.meta.versioning !== "Enabled") {
      throw new S3Error("InvalidRequest", "Versioning must be 'Enabled' on the bucket to apply a replication configuration");
    }
  } else if (sub === "object-lock") {
    if (text(root, "ObjectLockEnabled") !== "Enabled") throw malformed();
    if (bucket.meta.versioning !== "Enabled") {
      throw new S3Error("InvalidBucketState", "Versioning must be 'Enabled' on the bucket to apply a Object Lock configuration", 409);
    }
    const mode = text(root, "Rule/DefaultRetention/Mode");
    if (mode && !["GOVERNANCE", "COMPLIANCE"].includes(mode)) throw malformed();
    if (mode && Boolean(text(root, "Rule/DefaultRetention/Days")) === Boolean(text(root, "Rule/DefaultRetention/Years"))) throw malformed();
  } else if (sub === "ownershipControls") {
    if (!["BucketOwnerPreferred", "ObjectWriter", "BucketOwnerEnforced"].includes(text(root, "Rule/ObjectOwnership"))) throw malformed();
  } else if (sub === "accelerate") {
    if (!["Enabled", "Suspended"].includes(text(root, "Status"))) throw malformed();
  } else if (sub === "requestPayment") {
    if (!["Requester", "BucketOwner"].includes(text(root, "Payer"))) throw malformed();
  } else if (sub === "encryption") {
    if (!["AES256", "aws:kms", "aws:kms:dsse"].includes(text(root, "Rule/ApplyServerSideEncryptionByDefault/SSEAlgorithm"))) throw malformed();
  }
  if (!isDict(bucket.meta.configs)) bucket.meta.configs = {};
  bucket.meta.configs[sub] = UTF8_STRICT.decode(body);
  if (sub === "object-lock") bucket.meta.object_lock = true;
  bucket.saveMeta();
}

module.exports = { CONFIGS, bucketConfig, setPolicy, setConfig };
