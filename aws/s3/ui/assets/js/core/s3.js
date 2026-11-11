// S3 names (ARNs, URIs, URLs) and the conversions between the server's XML configurations and the console's forms
// or the JSON the AWS console shows (CORS, website routing rules).

const NS = "http://s3.amazonaws.com/doc/2006-03-01/";

export const bucketArn = (bucket) => `arn:aws:s3:::${bucket}`;
export const objectArn = (bucket, key) => `arn:aws:s3:::${bucket}/${key}`;
export const s3Uri = (bucket, key) => `s3://${bucket}/${key || ""}`;

/** Percent-encode a key for a URL path, keeping "/" readable. */
export function encodeKey(key) {
  return String(key)
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
}

/** The path-style object URL on this server. */
export function objectUrl(bucket, key) {
  return `${location.origin}/${encodeURIComponent(bucket)}/${encodeKey(key)}`;
}

export function escapeXml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}

const tag = (name, value) => `<${name}>${escapeXml(value)}</${name}>`;

// ----------------------------------------------------------------------------- XML reading

export function parseXml(text) {
  if (!text || !String(text).trim()) return null;
  const doc = new DOMParser().parseFromString(String(text), "application/xml");
  if (doc.getElementsByTagName("parsererror").length) return null;
  return doc.documentElement;
}

/** Child elements named `name` (any namespace). */
export function kids(el, name) {
  if (!el) return [];
  return Array.from(el.children).filter((c) => c.localName === name);
}

export function kid(el, name) {
  return kids(el, name)[0] || null;
}

/** Text at a "A/B/C" path below el ("" when missing). */
export function txt(el, path) {
  let node = el;
  for (const part of path.split("/")) {
    node = kid(node, part);
    if (!node) return "";
  }
  return (node.textContent || "").trim();
}

const num = (value) => (value === "" || value === undefined || value === null ? null : Number(value));

// ----------------------------------------------------------------------------- access

/** "public" | "objects-can-be-public" | "not-public" (uses the server's value when it has one). */
export function accessOf(entry) {
  if (!entry) return "objects-can-be-public";
  if (entry.access) return entry.access;
  if (entry.public || entry.policyPublic) return "public";
  const b = entry.publicBlock;
  if (b && b.BlockPublicAcls && b.IgnorePublicAcls && b.BlockPublicPolicy && b.RestrictPublicBuckets) return "not-public";
  return "objects-can-be-public";
}

export const ACCESS_TEXT = {
  public: "Public",
  "objects-can-be-public": "Objects can be public",
  "not-public": "Bucket and objects not public",
};

// ----------------------------------------------------------------------------- block public access, ownership

export const BPA_FLAGS = ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"];

export function publicAccessBlockXml(flags) {
  return `<PublicAccessBlockConfiguration xmlns="${NS}">${BPA_FLAGS.map((f) => tag(f, flags[f] ? "true" : "false")).join("")}</PublicAccessBlockConfiguration>`;
}

export function ownershipXml(value) {
  return `<OwnershipControls xmlns="${NS}"><Rule>${tag("ObjectOwnership", value)}</Rule></OwnershipControls>`;
}

/** The bucket's object ownership: from BucketInfo.ownership, else from the stored XML. */
export function ownershipOf(info) {
  if (info && typeof info.ownership === "string") return info.ownership;
  const root = parseXml(info && info.configs ? info.configs.ownershipControls : "");
  return root ? txt(root, "Rule/ObjectOwnership") : "";
}

export const OWNERSHIP_TEXT = {
  BucketOwnerEnforced: "Bucket owner enforced",
  BucketOwnerPreferred: "Bucket owner preferred",
  ObjectWriter: "Object writer",
  "": "Object writer",
};

// ----------------------------------------------------------------------------- ACLs (canned <-> grantee table)

/** The grantee checkboxes for a canned bucket ACL. */
export function bucketAclGrants(canned) {
  return {
    everyone: { list: canned === "public-read" || canned === "public-read-write", write: canned === "public-read-write" },
    authenticated: { list: canned === "authenticated-read", write: false },
  };
}

export function cannedFromGrants(g) {
  if (g.everyone.write) return "public-read-write";
  if (g.everyone.list) return "public-read";
  if (g.authenticated.list) return "authenticated-read";
  return "private";
}

// ----------------------------------------------------------------------------- object lock

export function objectLockOf(info) {
  const root = parseXml(info && info.configs ? info.configs["object-lock"] : "");
  const out = { enabled: Boolean(info && info.objectLock), mode: "", days: null, years: null };
  if (root) {
    out.enabled = out.enabled || txt(root, "ObjectLockEnabled") === "Enabled";
    out.mode = txt(root, "Rule/DefaultRetention/Mode");
    out.days = num(txt(root, "Rule/DefaultRetention/Days"));
    out.years = num(txt(root, "Rule/DefaultRetention/Years"));
  }
  return out;
}

export function objectLockXml({ mode, days, years }) {
  let rule = "";
  if (mode) {
    const period = years ? tag("Years", years) : tag("Days", days);
    rule = `<Rule><DefaultRetention>${tag("Mode", mode)}${period}</DefaultRetention></Rule>`;
  }
  return `<ObjectLockConfiguration xmlns="${NS}"><ObjectLockEnabled>Enabled</ObjectLockEnabled>${rule}</ObjectLockConfiguration>`;
}

// ----------------------------------------------------------------------------- CORS (XML <-> AWS console JSON)

export const CORS_METHODS = ["GET", "PUT", "POST", "DELETE", "HEAD"];

export function corsFromXml(xml) {
  const root = parseXml(xml);
  if (!root) return [];
  return kids(root, "CORSRule").map((rule) => {
    const out = {};
    const id = txt(rule, "ID");
    if (id) out.ID = id;
    out.AllowedHeaders = kids(rule, "AllowedHeader").map((e) => e.textContent.trim());
    out.AllowedMethods = kids(rule, "AllowedMethod").map((e) => e.textContent.trim());
    out.AllowedOrigins = kids(rule, "AllowedOrigin").map((e) => e.textContent.trim());
    out.ExposeHeaders = kids(rule, "ExposeHeader").map((e) => e.textContent.trim());
    const age = txt(rule, "MaxAgeSeconds");
    if (age) out.MaxAgeSeconds = Number(age);
    return out;
  });
}

function strings(value, name, index) {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.some((v) => typeof v !== "string")) {
    throw new Error(`Rule ${index + 1}: ${name} must be an array of strings.`);
  }
  return value;
}

/** Checks the AWS console JSON and returns the XML ("" for an empty list, which deletes the configuration). */
export function corsToXml(rules) {
  if (!Array.isArray(rules)) throw new Error("The CORS configuration must be a JSON array of rules.");
  if (!rules.length) return "";
  if (rules.length > 100) throw new Error("A CORS configuration can have at most 100 rules.");
  const known = ["ID", "AllowedHeaders", "AllowedMethods", "AllowedOrigins", "ExposeHeaders", "MaxAgeSeconds"];
  const body = rules
    .map((rule, i) => {
      if (!rule || typeof rule !== "object" || Array.isArray(rule)) throw new Error(`Rule ${i + 1} must be an object.`);
      const unknown = Object.keys(rule).filter((k) => !known.includes(k));
      if (unknown.length) throw new Error(`Rule ${i + 1}: unknown field ${unknown[0]}.`);
      const methods = strings(rule.AllowedMethods, "AllowedMethods", i);
      const origins = strings(rule.AllowedOrigins, "AllowedOrigins", i);
      if (!methods.length) throw new Error(`Rule ${i + 1}: AllowedMethods is required.`);
      if (!origins.length) throw new Error(`Rule ${i + 1}: AllowedOrigins is required.`);
      const bad = methods.find((m) => !CORS_METHODS.includes(m));
      if (bad) throw new Error(`Rule ${i + 1}: unsupported method ${bad} (use ${CORS_METHODS.join(", ")}).`);
      if (rule.MaxAgeSeconds !== undefined && !(Number.isInteger(rule.MaxAgeSeconds) && rule.MaxAgeSeconds >= 0)) {
        throw new Error(`Rule ${i + 1}: MaxAgeSeconds must be a whole number of seconds.`);
      }
      return (
        "<CORSRule>" +
        (rule.ID ? tag("ID", rule.ID) : "") +
        strings(rule.AllowedHeaders, "AllowedHeaders", i).map((v) => tag("AllowedHeader", v)).join("") +
        methods.map((v) => tag("AllowedMethod", v)).join("") +
        origins.map((v) => tag("AllowedOrigin", v)).join("") +
        strings(rule.ExposeHeaders, "ExposeHeaders", i).map((v) => tag("ExposeHeader", v)).join("") +
        (rule.MaxAgeSeconds !== undefined ? tag("MaxAgeSeconds", rule.MaxAgeSeconds) : "") +
        "</CORSRule>"
      );
    })
    .join("");
  return `<CORSConfiguration xmlns="${NS}">${body}</CORSConfiguration>`;
}

// ----------------------------------------------------------------------------- static website hosting

const CONDITION_KEYS = ["KeyPrefixEquals", "HttpErrorCodeReturnedEquals"];
const REDIRECT_KEYS = ["HostName", "HttpRedirectCode", "Protocol", "ReplaceKeyPrefixWith", "ReplaceKeyWith"];

/** {enabled, mode: "website"|"redirect", index, error, routingRules: [...AWS JSON], host, protocol} */
export function websiteFromXml(xml) {
  const root = parseXml(xml);
  const out = { enabled: Boolean(root), mode: "website", index: "index.html", error: "", routingRules: [], host: "", protocol: "" };
  if (!root) return out;
  const all = kid(root, "RedirectAllRequestsTo");
  if (all) {
    out.mode = "redirect";
    out.host = txt(all, "HostName");
    out.protocol = txt(all, "Protocol");
    return out;
  }
  out.index = txt(root, "IndexDocument/Suffix");
  out.error = txt(root, "ErrorDocument/Key");
  out.routingRules = kids(kid(root, "RoutingRules"), "RoutingRule").map((rule) => {
    const item = {};
    const cond = kid(rule, "Condition");
    if (cond) {
      item.Condition = {};
      for (const k of CONDITION_KEYS) if (kid(cond, k)) item.Condition[k] = txt(cond, k);
    }
    const red = kid(rule, "Redirect");
    item.Redirect = {};
    for (const k of REDIRECT_KEYS) if (red && kid(red, k)) item.Redirect[k] = txt(red, k);
    return item;
  });
  return out;
}

function routingRulesXml(rules) {
  if (!Array.isArray(rules)) throw new Error("Redirection rules must be a JSON array.");
  if (!rules.length) return "";
  const body = rules
    .map((rule, i) => {
      if (!rule || typeof rule !== "object" || !rule.Redirect || typeof rule.Redirect !== "object") {
        throw new Error(`Redirection rule ${i + 1} needs a Redirect object.`);
      }
      let cond = "";
      if (rule.Condition) {
        const parts = CONDITION_KEYS.filter((k) => rule.Condition[k] !== undefined).map((k) => tag(k, rule.Condition[k]));
        if (parts.length) cond = `<Condition>${parts.join("")}</Condition>`;
      }
      const unknown = Object.keys(rule.Redirect).filter((k) => !REDIRECT_KEYS.includes(k));
      if (unknown.length) throw new Error(`Redirection rule ${i + 1}: unknown Redirect field ${unknown[0]}.`);
      if (rule.Redirect.ReplaceKeyPrefixWith !== undefined && rule.Redirect.ReplaceKeyWith !== undefined) {
        throw new Error(`Redirection rule ${i + 1}: use ReplaceKeyPrefixWith or ReplaceKeyWith, not both.`);
      }
      const red = REDIRECT_KEYS.filter((k) => rule.Redirect[k] !== undefined).map((k) => tag(k, rule.Redirect[k]));
      return `<RoutingRule>${cond}<Redirect>${red.join("")}</Redirect></RoutingRule>`;
    })
    .join("");
  return `<RoutingRules>${body}</RoutingRules>`;
}

export function websiteToXml(cfg) {
  if (cfg.mode === "redirect") {
    if (!cfg.host) throw new Error("Enter the host name to redirect to.");
    const proto = cfg.protocol ? tag("Protocol", cfg.protocol) : "";
    return `<WebsiteConfiguration xmlns="${NS}"><RedirectAllRequestsTo>${tag("HostName", cfg.host)}${proto}</RedirectAllRequestsTo></WebsiteConfiguration>`;
  }
  if (!cfg.index) throw new Error("Enter an index document.");
  if (cfg.index.includes("/")) throw new Error("The index document name cannot contain a slash (/).");
  const error = cfg.error ? `<ErrorDocument>${tag("Key", cfg.error)}</ErrorDocument>` : "";
  return `<WebsiteConfiguration xmlns="${NS}"><IndexDocument>${tag("Suffix", cfg.index)}</IndexDocument>${error}${routingRulesXml(cfg.routingRules || [])}</WebsiteConfiguration>`;
}

// ----------------------------------------------------------------------------- lifecycle

export const TRANSITION_CLASSES = ["STANDARD_IA", "INTELLIGENT_TIERING", "ONEZONE_IA", "GLACIER_IR", "GLACIER", "DEEP_ARCHIVE"];

/** A lifecycle rule as the console edits it. */
export function emptyRule() {
  return {
    id: "",
    status: "Enabled",
    filtered: true,
    prefix: "",
    tags: {},
    sizeGt: null,
    sizeLt: null,
    transitions: [],
    ncTransitions: [],
    expirationDays: null,
    expirationDate: "",
    expiredMarker: false,
    ncExpirationDays: null,
    ncNewer: null,
    abortDays: null,
  };
}

export function lifecycleFromXml(xml) {
  const root = parseXml(xml);
  if (!root) return [];
  return kids(root, "Rule").map((rule) => {
    const r = emptyRule();
    r.id = txt(rule, "ID");
    r.status = txt(rule, "Status") || "Enabled";
    const filter = kid(rule, "Filter");
    r.prefix = txt(rule, "Prefix");
    if (filter) {
      const scope = kid(filter, "And") || filter;
      r.prefix = txt(scope, "Prefix") || r.prefix;
      for (const t of kids(scope, "Tag")) r.tags[txt(t, "Key")] = txt(t, "Value");
      r.sizeGt = num(txt(scope, "ObjectSizeGreaterThan"));
      r.sizeLt = num(txt(scope, "ObjectSizeLessThan"));
    }
    r.filtered = Boolean(r.prefix || Object.keys(r.tags).length || r.sizeGt !== null || r.sizeLt !== null);
    r.transitions = kids(rule, "Transition").map((t) => ({
      days: num(txt(t, "Days")),
      date: txt(t, "Date"),
      storageClass: txt(t, "StorageClass"),
    }));
    r.ncTransitions = kids(rule, "NoncurrentVersionTransition").map((t) => ({
      days: num(txt(t, "NoncurrentDays")),
      newer: num(txt(t, "NewerNoncurrentVersions")),
      storageClass: txt(t, "StorageClass"),
    }));
    const exp = kid(rule, "Expiration");
    if (exp) {
      r.expirationDays = num(txt(exp, "Days"));
      r.expirationDate = txt(exp, "Date");
      r.expiredMarker = txt(exp, "ExpiredObjectDeleteMarker").toLowerCase() === "true";
    }
    const nce = kid(rule, "NoncurrentVersionExpiration");
    if (nce) {
      r.ncExpirationDays = num(txt(nce, "NoncurrentDays"));
      r.ncNewer = num(txt(nce, "NewerNoncurrentVersions"));
    }
    const abort = kid(rule, "AbortIncompleteMultipartUpload");
    if (abort) r.abortDays = num(txt(abort, "DaysAfterInitiation"));
    return r;
  });
}

function filterXml(r) {
  if (!r.filtered) return "<Filter></Filter>";
  const parts = [];
  if (r.prefix) parts.push(tag("Prefix", r.prefix));
  for (const [k, v] of Object.entries(r.tags || {})) parts.push(`<Tag>${tag("Key", k)}${tag("Value", v)}</Tag>`);
  if (r.sizeGt !== null && r.sizeGt !== undefined) parts.push(tag("ObjectSizeGreaterThan", r.sizeGt));
  if (r.sizeLt !== null && r.sizeLt !== undefined) parts.push(tag("ObjectSizeLessThan", r.sizeLt));
  if (parts.length > 1) return `<Filter><And>${parts.join("")}</And></Filter>`;
  return `<Filter>${parts.join("")}</Filter>`;
}

function ruleXml(r) {
  let out = "<Rule>" + tag("ID", r.id) + filterXml(r) + tag("Status", r.status);
  for (const t of r.transitions) {
    out += `<Transition>${t.date ? tag("Date", t.date) : tag("Days", t.days)}${tag("StorageClass", t.storageClass)}</Transition>`;
  }
  for (const t of r.ncTransitions) {
    const newer = t.newer ? tag("NewerNoncurrentVersions", t.newer) : "";
    out += `<NoncurrentVersionTransition>${tag("NoncurrentDays", t.days)}${newer}${tag("StorageClass", t.storageClass)}</NoncurrentVersionTransition>`;
  }
  if (r.expirationDays || r.expirationDate) {
    out += `<Expiration>${r.expirationDate ? tag("Date", r.expirationDate) : tag("Days", r.expirationDays)}</Expiration>`;
  } else if (r.expiredMarker) {
    out += "<Expiration><ExpiredObjectDeleteMarker>true</ExpiredObjectDeleteMarker></Expiration>";
  }
  if (r.ncExpirationDays) {
    const newer = r.ncNewer ? tag("NewerNoncurrentVersions", r.ncNewer) : "";
    out += `<NoncurrentVersionExpiration>${tag("NoncurrentDays", r.ncExpirationDays)}${newer}</NoncurrentVersionExpiration>`;
  }
  if (r.abortDays) out += `<AbortIncompleteMultipartUpload>${tag("DaysAfterInitiation", r.abortDays)}</AbortIncompleteMultipartUpload>`;
  return out + "</Rule>";
}

/** The whole configuration ("" when there are no rules, which deletes it). */
export function lifecycleToXml(rules) {
  if (!rules.length) return "";
  return `<LifecycleConfiguration xmlns="${NS}">${rules.map(ruleXml).join("")}</LifecycleConfiguration>`;
}

/** One-line summaries for the lifecycle rules table. */
export function ruleSummary(r) {
  const cls = (c) => c.replace(/_/g, " ");
  const current = [];
  for (const t of r.transitions) current.push(`Transition to ${cls(t.storageClass)} ${t.date ? "on " + t.date.slice(0, 10) : `after ${t.days} days`}`);
  if (r.expirationDays) current.push(`Expire after ${r.expirationDays} days`);
  if (r.expirationDate) current.push(`Expire on ${r.expirationDate.slice(0, 10)}`);
  const noncurrent = [];
  for (const t of r.ncTransitions) noncurrent.push(`Transition to ${cls(t.storageClass)} after ${t.days} days`);
  if (r.ncExpirationDays) noncurrent.push(`Delete after ${r.ncExpirationDays} days` + (r.ncNewer ? `, keep ${r.ncNewer} newer` : ""));
  return {
    scope: r.filtered ? "Filtered" : "Entire bucket",
    current: current.join("; ") || "-",
    noncurrent: noncurrent.join("; ") || "-",
    markers: r.expiredMarker ? "Delete" : "-",
    multipart: r.abortDays ? `Delete after ${r.abortDays} days` : "-",
  };
}
