"use strict";
// An Amazon S3 compatible server (Node.js, no dependencies).
//
// boto3, the AWS SDKs (JavaScript v3, Java, Go, ...), the AWS CLI (`aws s3` and `aws s3api`), rclone, s3cmd and
// pskit's `s3` storage driver talk to it unchanged: point their endpoint at this server and sign with an access key /
// secret key it knows. Requests are checked with AWS Signature Version 4 (headers, presigned URLs, streaming chunk
// signatures, browser POST policies) or Version 2, so a wrong secret key is refused.
//
// Buckets: create / delete / head / list, location, versioning (Enabled / Suspended), tags, policies (anonymous access
// follows them), ACLs (canned and grants), CORS (applied), lifecycle rules (applied: expiration, noncurrent versions,
// delete markers, incomplete uploads, transitions), static website hosting, object lock (governance / compliance
// retention, legal hold), public access block, ownership controls, default encryption, and logging, notification,
// replication, accelerate, request payment, metrics, analytics, inventory and intelligent-tiering configurations
// (stored and returned).
//
// Objects: put / get / head / delete / copy, ranges, part numbers, conditional requests (also on writes), user
// metadata and standard headers, response header overrides, tags, ACLs, storage classes, checksums (CRC32, CRC32C,
// CRC64NVME, SHA1, SHA256, Content-MD5), version ids and delete markers, multi-object delete, GetObjectAttributes,
// restore (archive storage classes), multipart uploads (upload part copy, list parts / uploads, composite and
// full-object checksums) and SSE headers (accepted and returned; the data is not encrypted at rest).
//
// A web console (/ui/) browses buckets and folders, uploads, downloads, copies, moves, deletes, shows versions, edits
// metadata and tags, makes share links and edits every bucket setting. It signs in with an access key and its secret
// key (or S3_UI_PASSWORD) and keeps the session in an HttpOnly cookie.
//
// Settings (environment), the same as the Python server (../python/server.py):
//   S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY   the credentials clients sign with
//   S3_CREDENTIALS                            more credentials: id1:secret1,id2:secret2
//   S3_AUTH                                   sigv4 (default: Signature Version 4 and 2) or off (development only)
//   S3_PORT (9000), S3_BIND (0.0.0.0), S3_DATA_DIR (./data), S3_REGION (us-east-1), S3_ACCOUNT_ID (000000000000)
//   S3_DOMAIN (localhost)                     comma-separated domains for virtual-hosted style (<bucket>.<domain>)
//   S3_UI (on), S3_UI_PASSWORD, S3_UI_FILE    the web console, a console password, and the console page
//   S3_MAX_OBJECT_SIZE (5 GiB), S3_MIN_PART_SIZE (5 MiB), S3_LIFECYCLE_INTERVAL (3600 seconds),
//   S3_LIFECYCLE_DAY_SECONDS (86400)          limits and the lifecycle sweep (a shorter "day" makes rules testable)
//
// The data lives under S3_DATA_DIR/buckets: bucket.json per bucket, one JSON record per key and one file per object
// version, in the same layout and formats as the Python server's, so the two servers can take turns on one data
// directory. `node server.js --check` exits 0 when the server answers on /-/health (a container health check).

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");
const zlib = require("zlib");

const VERSION = "1.0.0";
const env = process.env;

class ValueError extends Error {}

const PY_WS = "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const STRIP_RE = new RegExp(`^[${PY_WS}]+|[${PY_WS}]+$`, "g");
const SPLIT_RE = new RegExp(`[${PY_WS}]+`);

/** str.strip() as Python does it (its whitespace set differs a little from String.prototype.trim). */
const pyStrip = (s) => String(s).replace(STRIP_RE, "");
/** str.split() without arguments. */
const pySplit = (s) => {
  const t = pyStrip(s);
  return t ? t.split(SPLIT_RE) : [];
};
/** bytes.strip(): ASCII whitespace only. */
const asciiStrip = (s) => s.replace(/^[ \t\n\r\x0b\x0c]+|[ \t\n\r\x0b\x0c]+$/g, "");

/** int() as Python parses it: surrounding whitespace, a sign and underscores between digits; else ValueError. */
function pyInt(value, base = 10) {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new ValueError("cannot convert float to integer");
    return Math.trunc(value);
  }
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value !== "string") throw new TypeError("int() argument must be a string or a number");
  let s = pyStrip(value);
  const re = base === 16 ? /^[+-]?(?:0[xX]_?)?[0-9a-fA-F](?:_?[0-9a-fA-F])*$/ : /^[+-]?[0-9](?:_?[0-9])*$/;
  if (!re.test(s)) throw new ValueError(`invalid literal for int() with base ${base}: '${value}'`);
  s = s.replace(/_/g, "");
  let negative = false;
  if (s[0] === "-" || s[0] === "+") {
    negative = s[0] === "-";
    s = s.slice(1);
  }
  if (base === 16) s = s.replace(/^0[xX]/, "");
  const n = parseInt(s, base);
  return negative ? -n : n;
}

function pyFloat(value) {
  const n = Number(pyStrip(value));
  if (Number.isNaN(n)) throw new ValueError(`could not convert string to float: '${value}'`);
  return n;
}

/** str() of a JSON value, as Python prints it. */
function pyStr(value) {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "object") return pyDumps(value);
  return String(value);
}

/** Python truthiness of a JSON value. */
function truthy(value) {
  if (value === null || value === undefined || value === false || value === 0 || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

const own = (obj, key) => obj !== null && typeof obj === "object" && Object.prototype.hasOwnProperty.call(obj, key);
/** dict.get(key, default). */
const g = (obj, key, def = undefined) => (own(obj, key) ? obj[key] : def);
/** params.get(): like dict.get, but a body that is not an object fails (Python's AttributeError, a 500). */
function pget(p, key, def = undefined) {
  if (p === null || typeof p !== "object" || Array.isArray(p)) throw new TypeError("the parameters are not an object");
  return g(p, key, def);
}
const nullObj = () => Object.create(null);

/** Python's string order (code points), which differs from UTF-16 order above U+FFFF. */
function cmpStr(a, b) {
  if (a === b) return 0;
  const n = Math.min(a.length, b.length);
  let i = 0;
  while (i < n && a.charCodeAt(i) === b.charCodeAt(i)) i++;
  if (i === n) return a.length - b.length;
  let x = a.charCodeAt(i);
  let y = b.charCodeAt(i);
  if (x >= 0xd800 && x <= 0xdfff) x += 0x2800;
  if (y >= 0xd800 && y <= 0xdfff) y += 0x2800;
  return x - y;
}

function bisectLeft(list, value) {
  let lo = 0;
  let hi = list.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cmpStr(list[mid], value) < 0) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function bisectRight(list, value) {
  let lo = 0;
  let hi = list.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cmpStr(value, list[mid]) < 0) hi = mid;
    else lo = mid + 1;
  }
  return lo;
}

const asciiJson = (s) =>
  JSON.stringify(s).replace(/[\u007f-￿]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`);

/** json.dumps: Python's separators (", " / ": ", or compact), ensure_ascii, optionally sort_keys. */
function pyDumps(value, sortKeys = false, compact = false) {
  const item = compact ? "," : ", ";
  const kv = compact ? ":" : ": ";
  const enc = (v) => {
    if (v === null || v === undefined) return "null";
    if (v === true) return "true";
    if (v === false) return "false";
    if (typeof v === "number") {
      if (Number.isFinite(v)) return JSON.stringify(v);
      return Number.isNaN(v) ? "NaN" : v > 0 ? "Infinity" : "-Infinity";
    }
    if (typeof v === "string") return asciiJson(v);
    if (Array.isArray(v)) return `[${v.map(enc).join(item)}]`;
    if (v instanceof Map) return enc(Object.fromEntries(v));
    const keys = Object.keys(v).filter((k) => v[k] !== undefined);
    if (sortKeys) keys.sort(cmpStr);
    return `{${keys.map((k) => asciiJson(k) + kv + enc(v[k])).join(item)}}`;
  };
  return enc(value);
}

const SAFE = new Set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~");

/** urllib.parse.quote(value, safe). */
function quote(value, safe = "/") {
  const bytes = Buffer.from(String(value), "utf8");
  let out = "";
  for (const b of bytes) {
    const c = String.fromCharCode(b);
    if (b < 128 && (SAFE.has(c) || safe.includes(c))) out += c;
    else out += `%${b < 16 ? "0" : ""}${b.toString(16).toUpperCase()}`;
  }
  return out;
}

const UTF8 = new TextDecoder("utf-8", { ignoreBOM: true });
const UTF8_STRICT = new TextDecoder("utf-8", { ignoreBOM: true, fatal: true });

/** urllib.parse.unquote: %XX runs decoded as UTF-8 (bad bytes become U+FFFD), "+" left alone. */
function unquote(s) {
  if (!s.includes("%")) return s;
  return s.replace(/(?:%[0-9A-Fa-f]{2})+/g, (run) => UTF8.decode(Buffer.from(run.replace(/%/g, ""), "hex")));
}

const PORT = pyInt(env.S3_PORT || "9000");
const BIND = env.S3_BIND || "0.0.0.0";
const DATA_DIR = env.S3_DATA_DIR ? path.normalize(env.S3_DATA_DIR).replace(/(.)[\\/]+$/, "$1") : path.join(process.cwd(), "data");
const REGION = env.S3_REGION || "us-east-1";
const ACCOUNT = env.S3_ACCOUNT_ID || "000000000000";
const AUTH = (env.S3_AUTH || "sigv4").toLowerCase();
const DOMAINS = (env.S3_DOMAIN || "localhost").split(",").map((d) => pyStrip(d).toLowerCase()).filter(Boolean);
const UI_ON = !["off", "0", "false", "no"].includes((env.S3_UI || "on").toLowerCase());
const UI_PASSWORD = env.S3_UI_PASSWORD || "";
const UI_FILE = env.S3_UI_FILE || "";
const MAX_OBJECT = pyInt(env.S3_MAX_OBJECT_SIZE || String(5 * 1024 ** 3));
const MIN_PART = pyInt(env.S3_MIN_PART_SIZE || String(5 * 1024 ** 2));
const LIFECYCLE_INTERVAL = pyFloat(env.S3_LIFECYCLE_INTERVAL || "3600");
const DAY = pyFloat(env.S3_LIFECYCLE_DAY_SECONDS || "86400");
const MAX_XML = 4 * 1024 * 1024;
const MAX_POST = 256 * 1024 * 1024;
const MAX_PARTS = 10000;
const SKEW = 15 * 60;
const SESSION_TTL = 12 * 3600;
const OWNER_ID = crypto.createHash("sha256").update(`pskit-s3:${ACCOUNT}`, "utf8").digest("hex");
const OWNER_NAME = "pskit";
const NS = "http://s3.amazonaws.com/doc/2006-03-01/";
const ALL_USERS = "http://acs.amazonaws.com/groups/global/AllUsers";
const AUTH_USERS = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers";
const LOG_DELIVERY = "http://acs.amazonaws.com/groups/s3/LogDelivery";
const STORAGE_CLASSES = ["STANDARD", "REDUCED_REDUNDANCY", "STANDARD_IA", "ONEZONE_IA", "INTELLIGENT_TIERING", "GLACIER",
  "DEEP_ARCHIVE", "GLACIER_IR", "OUTPOSTS", "SNOW", "EXPRESS_ONEZONE"];
const ARCHIVED = ["GLACIER", "DEEP_ARCHIVE"];
const CANNED = ["private", "public-read", "public-read-write", "authenticated-read", "aws-exec-read", "bucket-owner-read",
  "bucket-owner-full-control", "log-delivery-write"];
const STD_HEADERS = ["cache-control", "content-disposition", "content-encoding", "content-language", "expires"];
const ALGORITHMS = ["CRC32", "CRC32C", "CRC64NVME", "SHA1", "SHA256"];
const BUCKET_RE = /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/;
const IP_RE = /^\d+\.\d+\.\d+\.\d+$/;
const AUTH4_RE = /^AWS4-HMAC-SHA256\s+Credential=([^,\s]+),\s*SignedHeaders=([^,\s]+),\s*Signature=([0-9a-f]{64})$/;
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
const BUCKET_SUBRESOURCES = ["acl", "cors", "delete", "encryption", "lifecycle", "location", "logging", "notification",
  "policy", "policyStatus", "replication", "requestPayment", "tagging", "uploads", "versioning", "versions", "website",
  "accelerate", "ownershipControls", "publicAccessBlock", "object-lock", "metrics", "analytics", "inventory",
  "intelligent-tiering"];
const OBJECT_SUBRESOURCES = ["acl", "tagging", "retention", "legal-hold", "attributes", "restore", "uploads", "uploadId",
  "select", "torrent"];
const V2_SUBRESOURCES = new Set(["acl", "cors", "delete", "lifecycle", "location", "logging", "notification",
  "partNumber", "policy", "requestPayment", "restore", "tagging", "torrent", "uploadId", "uploads", "versionId",
  "versioning", "versions", "website", "response-cache-control", "response-content-disposition",
  "response-content-encoding", "response-content-language", "response-content-type", "response-expires", "retention",
  "legal-hold", "object-lock", "encryption", "accelerate", "publicAccessBlock", "ownershipControls", "replication",
  "attributes", "policyStatus"]);

function credentialsFromEnv() {
  // A Map keeps the order credentials were given in (the console's share links use the first one).
  const out = new Map();
  if (env.S3_SECRET_ACCESS_KEY) out.set(env.S3_ACCESS_KEY_ID || "pskit", env.S3_SECRET_ACCESS_KEY);
  for (const pair of (env.S3_CREDENTIALS || "").split(",")) {
    const item = pyStrip(pair);
    const at = item.indexOf(":");
    if (at < 0) continue;
    const key = item.slice(0, at);
    const secret = item.slice(at + 1);
    if (key && secret) out.set(key, secret);
  }
  return out;
}

const CREDENTIALS = credentialsFromEnv();

function log(...parts) {
  console.log(new Date().toISOString().replace(/\.\d+Z$/, "+00:00"), ...parts);
}

class S3Error extends Error {
  constructor(code, message, status = 400, extra = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.extra = extra;
    this.headers = {};
  }
}

const noBucket = (name) => new S3Error("NoSuchBucket", "The specified bucket does not exist", 404, { BucketName: name });
const noKey = (key) => new S3Error("NoSuchKey", "The specified key does not exist.", 404, { Key: key });
const invalid = (message, name = "", value = "") =>
  new S3Error("InvalidArgument", message, 400, name ? { ArgumentName: name, ArgumentValue: value } : {});
const malformed = () =>
  new S3Error("MalformedXML", "The XML you provided was not well-formed or did not validate against our published schema");
const denied = (message = "Access Denied") => new S3Error("AccessDenied", message, 403);
const notAllowed = () => new S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405);
const preconditionFailed = (condition) =>
  new S3Error("PreconditionFailed", "At least one of the pre-conditions you specified did not hold", 412,
    condition ? { Condition: condition } : {});

// ----------------------------------------------------------------------------- formats

const epoch = () => Date.now() / 1000;
const now3 = () => Math.round(Date.now()) / 1000;

function iso(ts) {
  const ms = Math.round(ts * 1000);
  const secs = Math.floor(Math.round(ts * 1e6) / 1e6);
  return `${new Date(secs * 1000).toISOString().slice(0, 19)}.${String(((ms % 1000) + 1000) % 1000).padStart(3, "0")}Z`;
}

const httpDate = (ts) => new Date(Math.trunc(ts) * 1000).toUTCString();
const amzStamp = (ts) => new Date(Math.floor(ts) * 1000).toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");

const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
const ZONES = { UT: 0, UTC: 0, GMT: 0, Z: 0, AST: -400, ADT: -300, EST: -500, EDT: -400, CST: -600, CDT: -500, MST: -700,
  MDT: -600, PST: -800, PDT: -700 };

function utcSeconds(y, mo, d, h, mi, s) {
  if (mo < 1 || mo > 12 || d < 1 || h > 23 || mi > 59 || s > 59 || y < 1) return null;
  const days = new Date(Date.UTC(2000, mo, 0)).getUTCDate() - (mo === 2 && !(y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)) ? 1 : 0);
  if (d > days) return null;
  const date = new Date(0);
  date.setUTCFullYear(y, mo - 1, d);
  date.setUTCHours(h, mi, s, 0);
  return date.getTime() / 1000;
}

/** Python's parse_time: an RFC 2822 date, an ISO 8601 date (naive means UTC) or a compact x-amz-date; else null. */
function parseTime(input) {
  const textIn = pyStrip(input || "");
  if (!textIn) return null;
  let m = /^(?:[A-Za-z]+,?\s*)?(\d{1,2})[\s-]+([A-Za-z]{3})[A-Za-z]*[\s-]+(\d{2,4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(?:\s*([A-Za-z]+|[+-]\d{4}))?\s*$/.exec(textIn);
  if (m && MONTHS[m[2].toLowerCase()]) {
    let year = Number(m[3]);
    if (year < 100) year += year > 68 ? 1900 : 2000;
    const base = utcSeconds(year, MONTHS[m[2].toLowerCase()], Number(m[1]), Number(m[4]), Number(m[5]), Number(m[6] || 0));
    if (base !== null) {
      let offset = 0;
      const zone = m[7] || "";
      if (/^[+-]\d{4}$/.test(zone)) offset = (zone[0] === "-" ? -1 : 1) * (Number(zone.slice(1, 3)) * 3600 + Number(zone.slice(3)) * 60);
      else if (ZONES[zone.toUpperCase()] !== undefined) offset = (ZONES[zone.toUpperCase()] / 100) * 3600;
      return base - offset;
    }
  }
  const cleaned = textIn.replace(/Z/g, "+00:00");
  m = /^(\d{4})(-?)(\d{2})\2(\d{2})(?:.(\d{2})(?::?(\d{2})(?::?(\d{2})(?:[.,](\d{1,9}))?)?)?(?:([+-])(\d{2})(?::?(\d{2})(?::?(\d{2})(?:\.(\d{1,6}))?)?)?)?)?$/.exec(cleaned);
  if (m) {
    const base = utcSeconds(Number(m[1]), Number(m[3]), Number(m[4]), Number(m[5] || 0), Number(m[6] || 0), Number(m[7] || 0));
    if (base !== null) {
      const frac = m[8] ? Number(`0.${m[8].slice(0, 6)}`) : 0;
      let offset = 0;
      if (m[9]) {
        if (Number(m[10]) > 23 || Number(m[11] || 0) > 59) return null;
        offset = (Number(m[10]) * 3600 + Number(m[11] || 0) * 60 + Number(m[12] || 0)) * (m[9] === "-" ? -1 : 1);
      }
      return base + frac - offset;
    }
  }
  return null;
}

function esc(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    .replace(/\r/g, "&#13;");
}

const x = (tag, value) => `<${tag}>${esc(value)}</${tag}>`;
const doc = (root, inner) => Buffer.from(`<?xml version="1.0" encoding="UTF-8"?>\n<${root} xmlns="${NS}">${inner}</${root}>`, "utf8");
const stripDecl = (xmlText) => xmlText.replace(/^\s*<\?xml[^>]*\?>\s*/, "");
const urlEnc = (value, enabled) => (enabled ? quote(value, "/") : value);
const ownerXml = () => `<Owner>${x("ID", OWNER_ID)}${x("DisplayName", OWNER_NAME)}</Owner>`;

// ----------------------------------------------------------------------------- XML (a small ElementTree)

class XmlElement {
  constructor(tag) {
    this.tag = tag;
    this.text = null; // null when there is no character data before the first child, as ElementTree
    this.children = [];
  }

  findall(pathText) {
    let nodes = [this];
    for (const part of pathText.split("/")) {
      const next = [];
      for (const node of nodes) for (const child of node.children) if (child.tag === part) next.push(child);
      nodes = next;
    }
    return nodes;
  }

  find(pathText) {
    return this.findall(pathText)[0] || null;
  }

  *iter(tag) {
    if (tag === undefined || this.tag === tag) yield this;
    for (const child of this.children) yield* child.iter(tag);
  }
}

const XML_START = /<([^\s<>/=!?"']+)((?:\s+[^\s=/>"'<]+\s*=\s*(?:"[^"<]*"|'[^'<]*'))*)\s*(\/?)>/y;
const XML_END = /<\/([^\s<>/=!?"']+)\s*>/y;

function xmlEntities(raw) {
  if (!raw.includes("&")) return raw;
  return raw.replace(/&([^;&<]*);?/g, (whole, name) => {
    if (!whole.endsWith(";")) throw new ValueError("not well-formed");
    const named = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" }[name];
    if (named) return named;
    const ref = /^#(?:x([0-9a-fA-F]+)|([0-9]+))$/.exec(name);
    if (!ref) throw new ValueError("undefined entity");
    const cp = ref[1] ? parseInt(ref[1], 16) : parseInt(ref[2], 10);
    const ok = cp === 0x9 || cp === 0xa || cp === 0xd || (cp >= 0x20 && cp <= 0xd7ff) || (cp >= 0xe000 && cp <= 0xfffd) ||
      (cp >= 0x10000 && cp <= 0x10ffff);
    if (!ok) throw new ValueError("reference to invalid character number");
    return String.fromCodePoint(cp);
  });
}

function parseXmlText(input) {
  const src = input.replace(/\r\n?/g, "\n");
  let i = src.charCodeAt(0) === 0xfeff ? 1 : 0;
  const stack = [];
  let root = null;
  const addText = (t) => {
    if (!t) return;
    if (!stack.length) {
      if (/[^ \t\n]/.test(t)) throw new ValueError("junk outside the root element");
      return;
    }
    const top = stack[stack.length - 1];
    if (!top.children.length) top.text = (top.text || "") + t;
  };
  while (i < src.length) {
    const lt = src.indexOf("<", i);
    const end = lt < 0 ? src.length : lt;
    if (end > i) addText(xmlEntities(src.slice(i, end)));
    if (lt < 0) break;
    i = lt;
    if (src.startsWith("<?", i)) {
      const e = src.indexOf("?>", i + 2);
      if (e < 0) throw new ValueError("unclosed processing instruction");
      i = e + 2;
    } else if (src.startsWith("<!--", i)) {
      const e = src.indexOf("-->", i + 4);
      if (e < 0) throw new ValueError("unclosed comment");
      i = e + 3;
    } else if (src.startsWith("<![CDATA[", i)) {
      const e = src.indexOf("]]>", i + 9);
      if (e < 0 || !stack.length) throw new ValueError("bad CDATA");
      addText(src.slice(i + 9, e));
      i = e + 3;
    } else if (src.startsWith("</", i)) {
      XML_END.lastIndex = i;
      const m = XML_END.exec(src);
      if (!m || !stack.length || stack[stack.length - 1].raw !== m[1]) throw new ValueError("mismatched tag");
      stack.pop();
      i = XML_END.lastIndex;
    } else {
      XML_START.lastIndex = i;
      const m = XML_START.exec(src);
      if (!m) throw new ValueError("not well-formed");
      if (!stack.length && root) throw new ValueError("junk after document element");
      const colon = m[1].indexOf(":");
      const el = new XmlElement(colon >= 0 ? m[1].slice(colon + 1) : m[1]);
      el.raw = m[1];
      if (m[2]) xmlEntities(m[2]);
      if (stack.length) stack[stack.length - 1].children.push(el);
      else root = el;
      if (!m[3]) stack.push(el);
      i = XML_START.lastIndex;
    }
  }
  if (!root || stack.length) throw new ValueError("no element found");
  return root;
}

function parseXml(body) {
  if (!asciiStrip(body.toString("latin1"))) throw malformed();
  if (body.includes("<!DOCTYPE") || body.includes("<!ENTITY")) throw malformed();
  try {
    return parseXmlText(UTF8_STRICT.decode(body));
  } catch {
    throw malformed();
  }
}

/** ElementTree's findtext with Python's strip: the default when the element or its text is missing. */
function text(el, pathText, def = "") {
  if (!el) return def;
  const found = el.find(pathText);
  return found && found.text !== null ? pyStrip(found.text) : def;
}

// ----------------------------------------------------------------------------- checksums

function crcTable(poly) {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ poly : c >>> 1;
    table[i] = c >>> 0;
  }
  return table;
}

const CRC32_TABLE = crcTable(0xedb88320);
const CRC32C_TABLE = crcTable(0x82f63b78);
// CRC64NVME (reflected polynomial 0x9A6C9329AC4BC9B5) as two 32-bit halves: fast, and no BigInt per byte.
const CRC64_HI = new Uint32Array(256);
const CRC64_LO = new Uint32Array(256);
for (let i = 0; i < 256; i++) {
  let hi = 0;
  let lo = i;
  for (let k = 0; k < 8; k++) {
    const carry = lo & 1;
    lo = ((lo >>> 1) | ((hi & 1) << 31)) >>> 0;
    hi >>>= 1;
    if (carry) {
      lo = (lo ^ 0xac4bc9b5) >>> 0;
      hi = (hi ^ 0x9a6c9329) >>> 0;
    }
  }
  CRC64_HI[i] = hi;
  CRC64_LO[i] = lo;
}

class Crc32 {
  constructor(table) {
    this.table = table;
    this.value = 0;
  }

  update(data) {
    if (!this.table && typeof zlib.crc32 === "function") {
      this.value = zlib.crc32(data, this.value);
      return this;
    }
    const t = this.table || CRC32_TABLE;
    let c = ~this.value >>> 0;
    for (let i = 0; i < data.length; i++) c = t[(c ^ data[i]) & 0xff] ^ (c >>> 8);
    this.value = ~c >>> 0;
    return this;
  }

  digest() {
    const out = Buffer.alloc(4);
    out.writeUInt32BE(this.value >>> 0);
    return out;
  }
}

class Crc64 {
  constructor() {
    this.hi = 0xffffffff;
    this.lo = 0xffffffff;
  }

  update(data) {
    let hi = this.hi;
    let lo = this.lo;
    for (let i = 0; i < data.length; i++) {
      const idx = (lo ^ data[i]) & 0xff;
      lo = (((lo >>> 8) | (hi << 24)) ^ CRC64_LO[idx]) >>> 0;
      hi = ((hi >>> 8) ^ CRC64_HI[idx]) >>> 0;
    }
    this.hi = hi;
    this.lo = lo;
    return this;
  }

  digest() {
    const out = Buffer.alloc(8);
    out.writeUInt32BE((this.hi ^ 0xffffffff) >>> 0, 0);
    out.writeUInt32BE((this.lo ^ 0xffffffff) >>> 0, 4);
    return out;
  }
}

function newChecksum(alg) {
  if (alg === "CRC32") return new Crc32(null);
  if (alg === "CRC32C") return new Crc32(CRC32C_TABLE);
  if (alg === "CRC64NVME") return new Crc64();
  if (alg === "SHA1") return crypto.createHash("sha1");
  if (alg === "SHA256") return crypto.createHash("sha256");
  throw invalid(`Checksum algorithm ${alg} is not supported.`, "x-amz-checksum-algorithm", alg);
}

const checksumOf = (alg, data) => newChecksum(alg).update(data).digest().toString("base64");
const checksumHeader = (alg) => `x-amz-checksum-${alg.toLowerCase()}`;
const checksumElement = (alg) => `Checksum${alg}`;
const md5Hex = (data) => crypto.createHash("md5").update(data).digest("hex");
const sha256Hex = (data) => crypto.createHash("sha256").update(data).digest("hex");
const hmacSha256 = (key, data) => crypto.createHmac("sha256", key).update(data, "utf8").digest();

function safeEqual(a, b) {
  const p = Buffer.from(String(a), "utf8");
  const q = Buffer.from(String(b), "utf8");
  return p.length === q.length && crypto.timingSafeEqual(p, q);
}

/** base64.b64decode(value, validate=True). */
function b64decodeStrict(value) {
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 !== 0) throw new ValueError("Invalid base64");
  return Buffer.from(value, "base64");
}

/** base64.b64decode(value) without validate: characters outside the alphabet are dropped, the padding is checked. */
function b64decodeLoose(value) {
  const cleaned = String(value).replace(/[^A-Za-z0-9+/=]/g, "");
  const data = cleaned.replace(/=+$/, "");
  if (data.includes("=") || data.length % 4 === 1 || (cleaned.length % 4 !== 0)) throw new ValueError("Incorrect padding");
  return Buffer.from(data, "base64");
}

// ----------------------------------------------------------------------------- store

// Node runs one piece of JavaScript at a time: every change to the in-memory state and its JSON files below is
// synchronous, so it happens as one step (the Python server takes a lock for the same sections). Only object bodies
// are streamed asynchronously, and the state is looked up again after each of those awaits.

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  const fd = fs.openSync(tmp, "w", 0o600);
  try {
    fs.writeSync(fd, Buffer.from(pyDumps(data, true, true), "utf8"));
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(tmp, file);
}

function unlink(file) {
  try {
    fs.unlinkSync(file);
  } catch {
    // open on Windows, or gone: the startup sweep removes blobs nothing refers to
  }
}

function rmTree(dir) {
  try {
    fs.rmSync(dir, { recursive: true, force: true });
  } catch {
    // ignore_errors, as shutil.rmtree
  }
}

function listDir(dir) {
  try {
    return fs.readdirSync(dir);
  } catch {
    return [];
  }
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

const keyHash = (key) => sha256Hex(Buffer.from(key, "utf8"));

class Bucket {
  constructor(dir, meta) {
    this.path = dir;
    this.meta = meta;
    this.objects = new Map(); // key -> {key, versions: [newest first]}
    this.uploads = new Map(); // upload id -> upload (with parts: Map of part number -> part)
    this.sorted = null;
    this.parsed = {};
  }

  get name() {
    return String(this.meta.name);
  }

  keys() {
    if (this.sorted === null) this.sorted = [...this.objects.keys()].sort(cmpStr);
    return this.sorted;
  }

  recordPath(key) {
    const h = keyHash(key);
    return path.join(this.path, "objects", h.slice(0, 2), `${h}.json`);
  }

  blobPath(blob) {
    return path.join(this.path, "blobs", blob.slice(0, 2), blob);
  }

  uploadDir(uploadId) {
    return path.join(this.path, "uploads", uploadId);
  }

  saveMeta() {
    this.parsed = {};
    writeJson(path.join(this.path, "bucket.json"), this.meta);
  }

  saveRecord(key) {
    const rec = this.objects.get(key);
    const file = this.recordPath(key);
    if (!rec || !rec.versions.length) {
      this.objects.delete(key);
      unlink(file);
      this.sorted = null;
      return;
    }
    writeJson(file, rec);
  }

  setRecord(key, rec) {
    if (!this.objects.has(key)) this.sorted = null;
    this.objects.set(key, rec);
    this.saveRecord(key);
  }
}

class Store {
  constructor(root) {
    this.root = root;
    this.buckets = new Map();
    this.tmp = path.join(root, "tmp");
    fs.mkdirSync(path.join(root, "buckets"), { recursive: true });
    rmTree(this.tmp);
    fs.mkdirSync(this.tmp, { recursive: true });
    for (const name of listDir(path.join(root, "buckets")).sort(cmpStr)) {
      const metaFile = path.join(root, "buckets", name, "bucket.json");
      if (!fs.existsSync(metaFile)) continue;
      let meta;
      try {
        meta = readJson(metaFile);
      } catch {
        log("skipping unreadable", metaFile);
        continue;
      }
      const bucket = new Bucket(path.dirname(metaFile), meta);
      this.load(bucket);
      this.buckets.set(bucket.name, bucket);
    }
  }

  load(bucket) {
    const used = new Set();
    const objects = path.join(bucket.path, "objects");
    for (const dir of listDir(objects)) {
      for (const name of listDir(path.join(objects, dir))) {
        if (!name.endsWith(".json")) continue;
        const file = path.join(objects, dir, name);
        let rec;
        try {
          rec = readJson(file);
        } catch {
          log("skipping unreadable", file);
          continue;
        }
        if (rec && truthy(rec.versions)) {
          bucket.objects.set(rec.key, rec);
          for (const v of rec.versions) if (v.blob) used.add(v.blob);
        }
      }
    }
    const uploads = path.join(bucket.path, "uploads");
    for (const dir of listDir(uploads)) {
      const upFile = path.join(uploads, dir, "upload.json");
      let up;
      try {
        up = readJson(upFile);
      } catch {
        continue;
      }
      up.parts = new Map();
      for (const name of listDir(path.join(uploads, dir))) {
        if (!name.endsWith(".json") || name === "upload.json") continue;
        let part;
        try {
          part = readJson(path.join(uploads, dir, name));
        } catch {
          continue;
        }
        if (fs.existsSync(path.join(uploads, dir, partName(part.n)))) up.parts.set(part.n, part);
      }
      bucket.uploads.set(up.id, up);
    }
    const blobs = path.join(bucket.path, "blobs");
    for (const dir of listDir(blobs)) {
      for (const name of listDir(path.join(blobs, dir))) if (!used.has(name)) unlink(path.join(blobs, dir, name));
    }
  }

  get(name) {
    const bucket = this.buckets.get(name);
    if (!bucket) throw noBucket(name);
    return bucket;
  }

  tempFile() {
    return path.join(this.tmp, crypto.randomBytes(16).toString("hex"));
  }

  commitBlob(bucket, tmp) {
    const blob = crypto.randomBytes(16).toString("hex");
    const dest = bucket.blobPath(blob);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.renameSync(tmp, dest);
    return blob;
  }
}

const partName = (n) => `${String(n).padStart(5, "0")}.part`;
const partJson = (n) => `${String(n).padStart(5, "0")}.json`;

let STORE = null;

// ----------------------------------------------------------------------------- request bodies

/** The request body as sent (Node has already removed HTTP chunked transfer coding), read on demand. */
class Raw {
  constructor(req, length, chunked) {
    this.req = req;
    this.iter = null;
    this.done = !chunked && !length;
    this.pieces = [];
    this.len = 0;
  }

  async fill() {
    if (this.done) return false;
    if (!this.iter) this.iter = this.req[Symbol.asyncIterator]();
    let r;
    try {
      r = await this.iter.next();
    } catch {
      this.done = true;
      throw new S3Error("IncompleteBody", "You did not provide the number of bytes specified by the Content-Length HTTP header");
    }
    if (r.done) {
      this.done = true;
      if (!this.req.complete) {
        throw new S3Error("IncompleteBody", "You did not provide the number of bytes specified by the Content-Length HTTP header");
      }
      return false;
    }
    if (r.value.length) {
      this.pieces.push(r.value);
      this.len += r.value.length;
    }
    return true;
  }

  take(n) {
    n = Math.max(0, Math.min(n, this.len));
    if (!n) return Buffer.alloc(0);
    const all = this.pieces.length === 1 ? this.pieces[0] : Buffer.concat(this.pieces);
    const out = all.subarray(0, n);
    const rest = all.subarray(n);
    this.pieces = rest.length ? [rest] : [];
    this.len = rest.length;
    return out;
  }

  async read(n) {
    while (this.len < n && !this.done) await this.fill();
    return this.take(n);
  }

  async readline(limit = 8192) {
    for (;;) {
      if (this.pieces.length > 1) this.pieces = [Buffer.concat(this.pieces)];
      const idx = this.pieces.length ? this.pieces[0].indexOf(10) : -1;
      if (idx >= 0) return this.take(idx + 1);
      if (this.done || this.len >= limit) return this.take(this.len);
      await this.fill();
    }
  }

  async *chunks() {
    if (this.len) yield this.take(this.len);
    while (!this.done) if ((await this.fill()) && this.len) yield this.take(this.len);
  }

  async drain() {
    // eslint-disable-next-line no-unused-vars
    for await (const _ of this.chunks());
  }
}

class Auth {
  constructor(principal, mode = "anonymous") {
    this.principal = principal;
    this.mode = mode;
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
      out.path = STORE.tempFile();
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

// ----------------------------------------------------------------------------- signatures

const uriEncode = (value, safe = "-_.~") => quote(value, safe);

function splitQuery(rawQuery) {
  const pairs = [];
  for (const part of rawQuery.split("&")) {
    if (!part) continue;
    const at = part.indexOf("=");
    pairs.push(at < 0 ? [unquote(part), ""] : [unquote(part.slice(0, at)), unquote(part.slice(at + 1))]);
  }
  return pairs;
}

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
      Object.assign(auth, { payload, key, signature, amzDate, scope });
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
  return auth;
}

// ----------------------------------------------------------------------------- access control

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

const isDict = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

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

const configsOf = (bucket) => (truthy(bucket.meta.configs) ? bucket.meta.configs : {});

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

function wild(pattern, value) {
  const regex = `^${pattern.split("*").map((p) => p.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&").replace(/\\\?/g, ".")).join(".*")}$`;
  return new RegExp(regex, pattern.toLowerCase().startsWith("s3:") ? "iu" : "u").test(value);
}

const asList = (value) => (Array.isArray(value) ? value : value !== null && value !== undefined ? [value] : []);

const principalIsAnyone = (principal) =>
  principal === "*" || (isDict(principal) && asList(g(principal, "AWS")).includes("*"));

/** "allow", "deny" or "" for an anonymous request under the bucket policy. */
function policyDecision(bucket, action, resource) {
  const raw = bucket.meta.policy;
  if (!raw) return "";
  let policy;
  try {
    policy = JSON.parse(raw);
  } catch {
    return "";
  }
  let decision = "";
  for (const st of asList(pget(policy, "Statement"))) {
    if (!isDict(st) || truthy(st.Condition) || own(st, "NotPrincipal")) continue;
    if (!principalIsAnyone(g(st, "Principal"))) continue;
    if (!asList(g(st, "Action")).some((a) => typeof a === "string" && wild(a, action))) continue;
    if (!asList(g(st, "Resource")).some((r) => typeof r === "string" && wild(r, resource))) continue;
    if (st.Effect === "Deny") return "deny";
    if (st.Effect === "Allow") decision = "allow";
  }
  return decision;
}

function statementsPublic(policy) {
  for (const st of asList(pget(policy, "Statement"))) {
    if (isDict(st) && st.Effect === "Allow" && !truthy(st.Condition) && principalIsAnyone(g(st, "Principal"))) return true;
  }
  return false;
}

function policyIsPublic(bucket) {
  const raw = bucket.meta.policy;
  if (!raw) return false;
  let policy;
  try {
    policy = JSON.parse(raw);
  } catch {
    return false;
  }
  return statementsPublic(policy);
}

function anonymousAllowed(bucket, action, key = "", version = null) {
  const block = publicBlock(bucket);
  const resource = `arn:aws:s3:::${bucket.name}${key ? `/${key}` : ""}`;
  if (!block.RestrictPublicBuckets) {
    const decision = policyDecision(bucket, action, resource);
    if (decision === "deny") return false;
    if (decision === "allow") return true;
  }
  if (block.IgnorePublicAcls || bucketOwnerEnforced(bucket)) return false;
  if (["s3:ListBucket", "s3:ListBucketVersions", "s3:ListBucketMultipartUploads"].includes(action)) return aclPublic(bucket.meta.acl, "READ");
  if (["s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"].includes(action)) {
    return aclPublic(bucket.meta.acl, "WRITE");
  }
  if (["s3:GetObject", "s3:GetObjectVersion"].includes(action) && version) return aclPublic(version.acl, "READ");
  return false;
}

// ----------------------------------------------------------------------------- CORS

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

// ----------------------------------------------------------------------------- lifecycle

function lifecycleRules(bucket) {
  if (own(bucket.parsed, "lifecycle")) return bucket.parsed.lifecycle;
  let rules = [];
  const raw = g(configsOf(bucket), "lifecycle");
  if (raw) {
    try {
      rules = parseLifecycle(Buffer.from(raw, "utf8"));
    } catch (err) {
      if (!(err instanceof S3Error)) throw err;
      rules = [];
    }
  }
  bucket.parsed.lifecycle = rules;
  return rules;
}

function num(value) {
  if (!value) return null;
  try {
    return pyInt(value);
  } catch {
    throw malformed();
  }
}

function parseLifecycle(body) {
  const root = parseXml(body);
  if (root.tag !== "LifecycleConfiguration") throw malformed();
  const rules = [];
  for (const rule of root.findall("Rule")) {
    const status = text(rule, "Status");
    if (status !== "Enabled" && status !== "Disabled") throw malformed();
    const flt = rule.find("Filter");
    let prefix = text(rule, "Prefix");
    const tags = {};
    let gt = null;
    let lt = null;
    if (flt) {
      const scope = flt.find("And") || flt;
      prefix = text(scope, "Prefix", prefix);
      for (const tag of scope.findall("Tag")) tags[text(tag, "Key")] = text(tag, "Value");
      gt = num(text(scope, "ObjectSizeGreaterThan"));
      lt = num(text(scope, "ObjectSizeLessThan"));
    }
    const exp = rule.find("Expiration");
    const nce = rule.find("NoncurrentVersionExpiration");
    const abort = rule.find("AbortIncompleteMultipartUpload");
    const transitions = rule.findall("Transition").map((tr) => ({
      days: num(text(tr, "Days")),
      date: parseTime(text(tr, "Date")),
      class: text(tr, "StorageClass"),
    }));
    const ncTransitions = rule.findall("NoncurrentVersionTransition").map((tr) => ({
      days: num(text(tr, "NoncurrentDays")),
      class: text(tr, "StorageClass"),
    }));
    const item = {
      id: text(rule, "ID"),
      enabled: status === "Enabled",
      prefix,
      tags,
      gt,
      lt,
      exp_days: num(text(exp, "Days")),
      exp_date: parseTime(text(exp, "Date")),
      exp_marker: text(exp, "ExpiredObjectDeleteMarker").toLowerCase() === "true",
      nc_days: num(text(nce, "NoncurrentDays")),
      nc_keep: num(text(nce, "NewerNoncurrentVersions")),
      abort_days: num(text(abort, "DaysAfterInitiation")),
      transitions,
      nc_transitions: ncTransitions,
    };
    if (item.exp_days !== null && item.exp_days < 1) throw invalid("'Days' for Expiration action must be a positive integer");
    rules.push(item);
  }
  if (!rules.length || rules.length > 1000) throw malformed();
  return rules;
}

function ruleMatches(rule, key, version) {
  if (!rule.enabled || !key.startsWith(rule.prefix)) return false;
  const tags = truthy(version.tags) ? version.tags : {};
  if (Object.entries(rule.tags).some(([k, v]) => g(tags, k) !== v)) return false;
  const size = pyInt(version.size || 0);
  if (rule.gt !== null && !(size > rule.gt)) return false;
  return !(rule.lt !== null && !(size < rule.lt));
}

/** Apply every bucket's lifecycle rules once. Returns how many changes were made. */
function sweepLifecycle(now = null) {
  now = now || epoch();
  let changes = 0;
  for (const bucket of [...STORE.buckets.values()]) {
    const rules = lifecycleRules(bucket);
    if (!rules.length) continue;
    for (const key of [...bucket.keys()]) {
      const rec = bucket.objects.get(key);
      if (!rec) continue;
      changes += sweepKey(bucket, key, rec, rules, now);
    }
    for (const [uploadId, up] of [...bucket.uploads]) {
      for (const rule of rules) {
        if (rule.enabled && rule.abort_days !== null && up.key.startsWith(rule.prefix) && now - up.initiated >= rule.abort_days * DAY) {
          abortUpload(bucket, uploadId);
          changes += 1;
          break;
        }
      }
    }
  }
  if (changes) log("lifecycle:", changes, "changes");
  return changes;
}

function sweepKey(bucket, key, rec, rules, now) {
  let changes = 0;
  const versions = rec.versions;
  const current = versions[0];
  for (const rule of rules) {
    if (!current.dm && ruleMatches(rule, key, current)) {
      let due = (rule.exp_days !== null && now - current.time >= rule.exp_days * DAY) || (rule.exp_date !== null && now >= rule.exp_date);
      if (due && !locked(current, now)) {
        deleteObject(bucket, key, null, false);
        return 1;
      }
      for (const tr of rule.transitions) {
        due = (tr.days !== null && now - current.time >= tr.days * DAY) || (tr.date !== null && now >= tr.date);
        if (due && tr.class && g(current, "class", "STANDARD") !== tr.class) {
          current.class = tr.class;
          bucket.saveRecord(key);
          changes += 1;
        }
      }
    }
  }
  const noncurrent = versions.slice(1);
  for (const rule of rules) {
    if (!rule.enabled || !key.startsWith(rule.prefix)) continue;
    if (rule.nc_days !== null) {
      let kept = 0;
      for (const version of [...noncurrent]) {
        if (version.dm) continue;
        if (rule.nc_keep !== null && kept < rule.nc_keep) {
          kept += 1;
          continue;
        }
        // A version becomes noncurrent when the next newer one is written.
        const since = versions.at(versions.indexOf(version) - 1).time;
        if (now - since >= rule.nc_days * DAY && !locked(version, now)) {
          removeVersion(bucket, key, version.id);
          changes += 1;
        }
      }
    }
    for (const tr of rule.nc_transitions) {
      for (const version of versions.slice(1)) {
        const since = versions.at(versions.indexOf(version) - 1).time;
        if (!version.dm && tr.days !== null && now - since >= tr.days * DAY && tr.class && g(version, "class", "STANDARD") !== tr.class) {
          version.class = tr.class;
          bucket.saveRecord(key);
          changes += 1;
        }
      }
    }
  }
  const after = bucket.objects.get(key);
  if (after && after.versions.length === 1 && after.versions[0].dm) {
    if (rules.some((r) => r.enabled && r.exp_marker && key.startsWith(r.prefix))) {
      removeVersion(bucket, key, after.versions[0].id);
      changes += 1;
    }
  }
  return changes;
}

function lifecycleLoop() {
  const tick = () => {
    try {
      sweepLifecycle();
    } catch (err) {
      log("lifecycle error:", String(err && err.message ? err.message : err));
    }
    setTimeout(tick, LIFECYCLE_INTERVAL * 1000).unref();
  };
  setTimeout(tick, Math.min(60, LIFECYCLE_INTERVAL) * 1000).unref();
}

// ----------------------------------------------------------------------------- object lock

function lockConfig(bucket) {
  const raw = g(configsOf(bucket), "object-lock", "");
  const out = { enabled: truthy(bucket.meta.object_lock), mode: "", days: 0, years: 0 };
  if (raw) {
    let root;
    try {
      root = parseXml(Buffer.from(raw, "utf8"));
    } catch (err) {
      if (err instanceof S3Error) return out;
      throw err;
    }
    out.enabled = out.enabled || text(root, "ObjectLockEnabled") === "Enabled";
    out.mode = text(root, "Rule/DefaultRetention/Mode");
    out.days = pyInt(text(root, "Rule/DefaultRetention/Days") || "0");
    out.years = pyInt(text(root, "Rule/DefaultRetention/Years") || "0");
  }
  return out;
}

function locked(version, now, bypass = false) {
  if (version.hold) return true;
  const retention = truthy(version.retention) ? version.retention : {};
  if (retention.until && retention.until > now) return !(retention.mode === "GOVERNANCE" && bypass);
  return false;
}

function checkUnlocked(version, bypass) {
  if (version.hold) throw denied("Access Denied because object protected by object lock.");
  if (locked(version, epoch(), bypass)) throw denied("Access Denied because object protected by object lock.");
}

// ----------------------------------------------------------------------------- bucket and object operations

const newVersionId = () => crypto.randomBytes(24).toString("base64url").replace(/-/g, ".");

function createBucket(name, region, acl, objectLock, ownership = "") {
  if (!BUCKET_RE.test(name) || name.includes("..") || IP_RE.test(name) || name.startsWith("xn--") ||
    name.endsWith("-s3alias") || name.endsWith("--ol-s3")) {
    throw new S3Error("InvalidBucketName", "The specified bucket is not valid.", 400, { BucketName: name });
  }
  if (STORE.buckets.has(name)) {
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
  const bucket = new Bucket(path.join(STORE.root, "buckets", name), meta);
  bucket.saveMeta();
  STORE.buckets.set(name, bucket);
  log("bucket created", name);
  return bucket;
}

function deleteBucket(name) {
  const bucket = STORE.get(name);
  if (bucket.objects.size) throw new S3Error("BucketNotEmpty", "The bucket you tried to delete is not empty", 409, { BucketName: name });
  for (const uploadId of [...bucket.uploads.keys()]) abortUpload(bucket, uploadId);
  STORE.buckets.delete(name);
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

const pyLen = (s) => [...s].length;

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

function readSource(headers, who) {
  const [srcBucketName, srcKey, srcVid] = copySource(headers);
  const srcBucket = STORE.get(srcBucketName);
  const version = findVersion(srcBucket, srcKey, srcVid);
  if (who === null && !anonymousAllowed(srcBucket, "s3:GetObject", srcKey, version)) throw denied();
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
  out.path = STORE.tempFile();
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

// ----------------------------------------------------------------------------- listing

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

const visible = (bucket) => (k) => {
  const rec = bucket.objects.get(k);
  return Boolean(rec) && !rec.versions[0].dm;
};

// ----------------------------------------------------------------------------- web console sessions

const SESSIONS = new Map();
const FAILURES = new Map();

function checkLogin(user, password) {
  if (UI_PASSWORD) return safeEqual(password, UI_PASSWORD);
  const secret = CREDENTIALS.get(user);
  // Compare against a dummy for an unknown user, so the time is the same.
  return safeEqual(password, secret === undefined ? "\0".repeat(32) : secret) && secret !== undefined;
}

function throttled(ip) {
  const t = epoch();
  const recent = (FAILURES.get(ip) || []).filter((f) => t - f < 300);
  FAILURES.set(ip, recent);
  return recent.length >= 10;
}

function failed(ip) {
  if (!FAILURES.has(ip)) FAILURES.set(ip, []);
  FAILURES.get(ip).push(epoch());
}

function newSession(user) {
  const sid = crypto.randomBytes(32).toString("base64url");
  const csrf = crypto.randomBytes(24).toString("base64url");
  const t = epoch();
  for (const [key, s] of SESSIONS) if (s.expires < t) SESSIONS.delete(key);
  SESSIONS.set(sid, { user, csrf, expires: t + SESSION_TTL });
  return [sid, csrf];
}

function sessionOf(cookieHeader) {
  for (const part of cookieHeader.split(";")) {
    const item = pyStrip(part);
    const at = item.indexOf("=");
    const name = at < 0 ? item : item.slice(0, at);
    const value = at < 0 ? "" : item.slice(at + 1);
    if (name === "s3_session") {
      const found = SESSIONS.get(value);
      if (found && found.expires > epoch()) return { ...found, id: value };
    }
  }
  return null;
}

function uiHtml() {
  const candidates = (UI_FILE ? [UI_FILE] : []).concat([path.join(__dirname, "index.html"), path.join(__dirname, "..", "ui", "index.html")]);
  for (const file of candidates) {
    try {
      if (fs.statSync(file).isFile()) return fs.readFileSync(file);
    } catch {
      // try the next one
    }
  }
  return Buffer.from("<!doctype html><title>S3 console</title><p>The console page (index.html) is missing.");
}

const UI_HEADERS = {
  "Cache-Control": "no-store",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
    "connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; " +
    "frame-src 'self' blob:; frame-ancestors 'none'; form-action 'self'",
};

function presign(method, host, bucket, key, expires, accessKey, versionId = "", scheme = "http") {
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
  if (versionId) pairs.push(["versionId", versionId]);
  const query = canonicalQuery(pairs);
  const canonical = [method, objectPath, query, `host:${host}\n`, "host", "UNSIGNED-PAYLOAD"].join("\n");
  const scope = `${day}/${REGION}/s3/aws4_request`;
  const toSign = ["AWS4-HMAC-SHA256", amzDate, scope, sha256Hex(Buffer.from(canonical, "utf8"))].join("\n");
  const signature = crypto.createHmac("sha256", signingKey(secret, day, REGION, "s3")).update(toSign, "utf8").digest("hex");
  return `${scheme}://${host}${objectPath}?${query}&X-Amz-Signature=${signature}`;
}

// ----------------------------------------------------------------------------- HTTP

function lowerHeaders(nreq) {
  const out = nullObj();
  const raw = nreq.rawHeaders;
  const names = [];
  const values = nullObj();
  for (let i = 0; i < raw.length; i += 2) {
    const low = raw[i].toLowerCase();
    if (values[low] === undefined) {
      values[low] = [];
      names.push(low);
    }
    values[low].push(pyStrip(raw[i + 1]));
  }
  for (const name of names) out[name] = values[name].join(",");
  return out;
}

/** urllib.parse.urlsplit's path and query of a request target. */
function splitTarget(target) {
  let rest = target;
  const scheme = /^[A-Za-z][A-Za-z0-9+.-]*:/.exec(rest);
  if (scheme && rest.slice(scheme[0].length, scheme[0].length + 2) === "//") rest = rest.slice(scheme[0].length);
  if (rest.startsWith("//")) {
    const m = /^\/\/[^/?#]*/.exec(rest);
    rest = rest.slice(m[0].length);
  }
  const hash = rest.indexOf("#");
  if (hash >= 0) rest = rest.slice(0, hash);
  const qi = rest.indexOf("?");
  return qi < 0 ? [rest, ""] : [rest.slice(0, qi), rest.slice(qi + 1)];
}

class Request {
  constructor(nreq) {
    this.nreq = nreq;
    this.method = nreq.method;
    const [rawPath, rawQuery] = splitTarget(nreq.url || "/");
    this.raw_path = rawPath || "/";
    this.raw_query = rawQuery;
    this.pairs = splitQuery(rawQuery);
    this.q = nullObj();
    for (const [k, v] of this.pairs) this.q[k] = v;
    this.headers = lowerHeaders(nreq);
    this.host = this.headers.host || "";
    this.bucket = "";
    this.key = "";
    this.vhost = "";
    this.auth = new Auth(null);
    this.ip = (nreq.socket && nreq.socket.remoteAddress) || "";
    const length = this.headers["content-length"];
    const chunked = (this.headers["transfer-encoding"] || "").toLowerCase().includes("chunked");
    let n = 0;
    if (length) {
      try {
        n = pyInt(length);
      } catch {
        throw new S3Error("InvalidArgument", "Content-Length is not valid.");
      }
    }
    this.raw = new Raw(nreq, n, chunked);
    this.consumed = !n && !chunked;
  }

  get who() {
    return this.auth.principal;
  }

  async smallBody(limit = MAX_XML) {
    this.consumed = true;
    const [, data] = await receive(this.raw, this.headers, this.auth, limit, "", "", false);
    return data;
  }

  async payload(alg, expected, limit = MAX_OBJECT) {
    this.consumed = true;
    const [received] = await receive(this.raw, this.headers, this.auth, limit, alg, expected);
    return received;
  }
}

class Response {
  constructor(status = 200, body = Buffer.alloc(0), headers = {}, ctype = "application/xml", file = null, start = 0, length = 0) {
    this.status = status;
    this.body = Buffer.isBuffer(body) ? body : Buffer.from(body, "utf8");
    this.headers = { ...headers };
    this.ctype = ctype;
    this.file = file;
    this.start = start;
    this.length = length;
  }
}

const xmlResponse = (root, inner, status = 200, headers = {}) => new Response(status, doc(root, inner), headers);
const jsonResponse = (data, headers = { "Cache-Control": "no-store" }, status = 200) =>
  new Response(status, Buffer.from(pyDumps(data), "utf8"), headers, "application/json");
const requestId = () => crypto.randomBytes(8).toString("hex").toUpperCase();

function errorResponse(exc, req, method) {
  const resource = req ? req.raw_path : "/";
  if (resource === "/ui" || resource.startsWith("/ui/")) {
    // The console reads JSON errors.
    return jsonResponse({ code: exc.code, message: exc.message }, { "Cache-Control": "no-store" }, exc.status);
  }
  const extra = Object.entries(exc.extra).filter(([, v]) => v).map(([k, v]) => x(k, v)).join("");
  const body = exc.status === 304 || method === "HEAD"
    ? Buffer.alloc(0)
    : Buffer.from(`<?xml version="1.0" encoding="UTF-8"?>\n<Error>${x("Code", exc.code)}${x("Message", exc.message)}` +
      `${extra}${x("Resource", resource)}${x("RequestId", requestId())}</Error>`, "utf8");
  const resp = new Response(exc.status, body, exc.headers);
  if (method === "HEAD" && exc.status !== 304 && resp.headers["Content-Type"] === undefined) resp.headers["Content-Type"] = "application/xml";
  return resp;
}

function sendResponse(nreq, res, resp, req) {
  const headers = { Server: `pskit-s3/${VERSION}`, "x-amz-request-id": requestId(), "x-amz-id-2": crypto.randomBytes(24).toString("base64") };
  Object.assign(headers, resp.headers);
  // The body was not read to its end (refused early, or an error mid-body): the rest of it must not be taken for
  // the next request on this connection.
  if (req && (!req.consumed || !req.raw.done)) headers.Connection = "close";
  const length = resp.file !== null ? resp.length : resp.body.length;
  if (resp.status !== 304 && resp.status !== 204) {
    if ((resp.body.length || resp.file !== null || resp.headers["Content-Type"] !== undefined) && headers["Content-Type"] === undefined) {
      headers["Content-Type"] = resp.ctype;
    }
    headers["Content-Length"] = String(length);
  } else if (resp.status === 204) {
    delete headers["Content-Length"];
  }
  try {
    res.writeHead(resp.status, headers);
  } catch (err) {
    // A header value Node refuses (Python's http.server fails the same way): drop the connection.
    log("error:", String(err.message || err));
    res.destroy();
    return;
  }
  if (nreq.method === "HEAD" || resp.status === 204 || resp.status === 304) {
    res.end();
    return;
  }
  if (resp.file !== null) {
    if (resp.length <= 0) {
      res.end();
      return;
    }
    const stream = fs.createReadStream(resp.file, { start: resp.start, end: resp.start + resp.length - 1, highWaterMark: 256 * 1024 });
    stream.on("error", () => res.destroy());
    res.on("close", () => stream.destroy());
    stream.pipe(res);
  } else {
    res.end(resp.body);
  }
}

const METHODS = new Set(["GET", "HEAD", "PUT", "POST", "DELETE", "OPTIONS"]);

/** The answer Python's http.server gives a method it has no handler for. */
function unsupportedMethod(nreq, res) {
  const body = Buffer.from("<!DOCTYPE HTML>\n<html lang=\"en\">\n    <head>\n        <meta charset=\"utf-8\">\n" +
    "        <title>Error response</title>\n    </head>\n    <body>\n        <h1>Error response</h1>\n" +
    "        <p>Error code: 501</p>\n" +
    `        <p>Message: Unsupported method ('${nreq.method.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}').</p>\n` +
    "        <p>Error code explanation: 501 - Server does not support this operation.</p>\n    </body>\n</html>\n", "utf8");
  res.writeHead(501, { Server: `pskit-s3/${VERSION}`, Connection: "close", "Content-Type": "text/html;charset=utf-8", "Content-Length": String(body.length) });
  res.end(body);
}

async function dispatch(nreq, res) {
  if (!METHODS.has(nreq.method)) {
    unsupportedMethod(nreq, res);
    return;
  }
  let req = null;
  let resp;
  try {
    req = new Request(nreq);
    resp = await route(req);
  } catch (err) {
    if (err instanceof S3Error) {
      resp = errorResponse(err, req, nreq.method);
    } else {
      log("error:", err && err.stack ? err.stack : String(err));
      resp = errorResponse(new S3Error("InternalError", "We encountered an internal error. Please try again.", 500), req, nreq.method);
    }
  }
  if (req && req.bucket && req.headers.origin !== undefined && req.method !== "OPTIONS") {
    const bucket = STORE.buckets.get(req.bucket);
    if (bucket) {
      const found = corsMatch(bucket, req.headers.origin, req.method, []);
      if (found) {
        delete found["Access-Control-Allow-Headers"];
        Object.assign(resp.headers, found);
      }
    }
  }
  sendResponse(nreq, res, resp, req);
}

function bucketFromHost(host) {
  const name = host.startsWith("[") ? "" : host.replace(/:[^:]*$/, "").toLowerCase();
  for (const domain of DOMAINS) if (name.endsWith(`.${domain}`)) return name.slice(0, -domain.length - 1);
  const match = /^(.+)\.s3[.-](?:[a-z0-9-]+\.)?amazonaws\.com$/.exec(name);
  return match ? match[1] : "";
}

async function route(req) {
  if (["/-/health", "/-/healthz"].includes(req.raw_path) ||
    (["/health", "/healthz"].includes(req.raw_path) && req.headers.authorization === undefined && !Object.keys(req.q).length)) {
    return new Response(200, pyDumps({ status: "ok", buckets: STORE.buckets.size, version: VERSION }), {}, "application/json");
  }
  if (req.raw_path === "/ui" || req.raw_path.startsWith("/ui/")) return uiRoute(req);
  if (req.raw_path.startsWith("/-/website/")) {
    const rest = req.raw_path.slice("/-/website/".length);
    const slash = rest.indexOf("/");
    const bucket = slash < 0 ? rest : rest.slice(0, slash);
    const key = slash < 0 ? "" : rest.slice(slash + 1);
    return website(req, unquote(bucket), unquote(key), `/-/website/${bucket}/`);
  }
  const hostBucket = bucketFromHost(req.host);
  const web = /^(.+)\.s3-website[.-]/.exec(req.host.toLowerCase());
  if (web) return website(req, web[1], unquote(req.raw_path.replace(/^\/+/, "")), "/");
  if (hostBucket) {
    req.vhost = hostBucket;
    req.bucket = hostBucket;
    req.key = unquote(req.raw_path.slice(1));
  } else {
    const rest = req.raw_path.slice(1);
    const slash = rest.indexOf("/");
    req.bucket = unquote(slash < 0 ? rest : rest.slice(0, slash));
    req.key = unquote(slash < 0 ? "" : rest.slice(slash + 1));
  }
  if (req.raw_path === "/" && !hostBucket && UI_ON && req.method === "GET" && req.headers.authorization === undefined &&
    req.q["X-Amz-Signature"] === undefined && (req.headers.accept || "").includes("text/html")) {
    return new Response(302, Buffer.alloc(0), { Location: "/ui/" }, "text/plain");
  }
  if (req.method === "OPTIONS") return preflight(req);
  if (req.method === "POST" && req.bucket && !req.key && (req.headers["content-type"] || "").startsWith("multipart/form-data") &&
    req.headers.authorization === undefined) {
    return postObject(req);
  }
  authenticate(req);
  const expectedOwner = req.headers["x-amz-expected-bucket-owner"];
  if (expectedOwner && expectedOwner !== ACCOUNT) throw denied();
  if (!req.bucket) {
    if (req.method === "GET") return listBuckets(req);
    throw notAllowed();
  }
  if (Buffer.byteLength(req.key, "utf8") > 1024) throw new S3Error("KeyTooLongError", "Your key is too long", 400);
  if (!req.key) return bucketRoute(req);
  return objectRoute(req);
}

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

function needAuth(req, bucket, action, key = "", version = null) {
  if (req.who !== null) return;
  if (bucket && anonymousAllowed(bucket, action, key, version)) return;
  throw denied();
}

function preflight(req) {
  const origin = req.headers.origin || "";
  const method = req.headers["access-control-request-method"] || "";
  if (!origin || !method) throw new S3Error("BadRequest", "Insufficient information. Origin request header needed.", 400);
  const bucket = STORE.buckets.get(req.bucket);
  if (!bucket) throw noBucket(req.bucket);
  if (!corsRules(bucket).length) throw new S3Error("CORSResponse", "CORS is not enabled for this bucket.", 403);
  const wanted = (req.headers["access-control-request-headers"] || "").split(",").filter((h) => pyStrip(h)).map((h) => pyStrip(h).toLowerCase());
  const found = corsMatch(bucket, origin, method.toUpperCase(), wanted);
  if (!found) {
    throw new S3Error("CORSResponse", "This CORS request is not allowed. This is usually because the evalution of " +
      "Origin, request method / Access-Control-Request-Method or Access-Control-Request-Headers are " +
      "not whitelisted by the resource's CORS spec.", 403);
  }
  return new Response(200, Buffer.alloc(0), found);
}

// ----------------------------------------------------------------------------- service and bucket routes

function listBuckets(req) {
  if (req.who === null) throw denied();
  const prefix = req.q.prefix || "";
  const region = req.q["bucket-region"] || "";
  const limit = pyInt(req.q["max-buckets"] || "10000");
  const after = req.q["continuation-token"] ? tokenDecode(req.q["continuation-token"]) : "";
  const names = [...STORE.buckets.keys()].sort(cmpStr).filter((n) => n.startsWith(prefix) && cmpStr(n, after) > 0 &&
    (!region || STORE.buckets.get(n).meta.region === region));
  const page = names.slice(0, Math.max(0, limit < 0 ? names.length + limit : limit));
  const more = names.length > limit;
  const items = page.map((n) => {
    const meta = STORE.buckets.get(n).meta;
    return `<Bucket>${x("Name", n)}${x("CreationDate", iso(meta.created))}${x("BucketRegion", meta.region || REGION)}</Bucket>`;
  }).join("");
  let inner = `${ownerXml()}<Buckets>${items}</Buckets>`;
  if (more) inner += x("ContinuationToken", tokenEncode(page[page.length - 1]));
  if (prefix) inner += x("Prefix", prefix);
  return xmlResponse("ListAllMyBucketsResult", inner);
}

async function bucketRoute(req) {
  const q = req.q;
  const method = req.method;
  const sub = BUCKET_SUBRESOURCES.find((s) => q[s] !== undefined) || "";
  if (method === "PUT" && !sub) return putBucket(req);
  if (method === "POST" && q.delete !== undefined) return deleteObjects(req);
  const bucket = STORE.get(req.bucket);
  if (method === "HEAD" && !sub) {
    needAuth(req, bucket, "s3:ListBucket");
    return new Response(200, Buffer.alloc(0), { "x-amz-bucket-region": bucket.meta.region || REGION, "x-amz-access-point-alias": "false" });
  }
  if (method === "DELETE" && !sub) {
    needAuth(req, null, "");
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
  needAuth(req, null, "");
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

const xmlDoc = (raw) => new Response(200, `<?xml version="1.0" encoding="UTF-8"?>\n${stripDecl(raw)}`);

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
  const bucket = STORE.get(req.bucket);
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
      if (req.who === null && !anonymousAllowed(bucket, "s3:DeleteObject", key)) throw denied();
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

// ----------------------------------------------------------------------------- object routes

async function objectRoute(req) {
  const q = req.q;
  const method = req.method;
  const bucket = STORE.get(req.bucket);
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
    const blob = STORE.commitBlob(bucket, received.path);
    received.path = null;
    version = putVersion(bucket, req.key, newVersion(received, fields, blob));
  } finally {
    if (received.path) unlink(received.path);
  }
  return new Response(200, Buffer.alloc(0), writeHeaders(version, bucket));
}

const FIELD_KEYS = ["type", "meta", "headers", "class", "tags", "acl", "sse", "redirect", "owner"];
const pick = (src, keys) => {
  const out = {};
  for (const k of keys) if (own(src, k)) out[k] = src[k];
  return out;
};

async function copyObject(req, bucket) {
  const [srcBucket, srcKey, src, srcPath] = readSource(req.headers, req.who);
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
    const blob = STORE.commitBlob(bucket, received.path);
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
  needAuth(req, null, "");
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
  needAuth(req, null, "");
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
  needAuth(req, null, "");
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
  needAuth(req, null, "");
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

// ----------------------------------------------------------------------------- multipart uploads

function createUpload(req, bucket) {
  const fields = objectFields(req.headers, bucket);
  const alg = (req.headers["x-amz-checksum-algorithm"] || "").toUpperCase();
  if (alg && !ALGORITHMS.includes(alg)) throw invalid(`Checksum algorithm ${alg} is not supported.`, "x-amz-checksum-algorithm", alg);
  const ctype = (req.headers["x-amz-checksum-type"] || (alg === "CRC64NVME" ? "FULL_OBJECT" : "COMPOSITE")).toUpperCase();
  if (!["COMPOSITE", "FULL_OBJECT"].includes(ctype)) throw invalid("Invalid checksum type", "x-amz-checksum-type", ctype);
  if (ctype === "FULL_OBJECT" && ["SHA1", "SHA256"].includes(alg)) {
    throw invalid("The FULL_OBJECT checksum type is not supported for this algorithm", "x-amz-checksum-type", ctype);
  }
  const uploadId = crypto.randomBytes(48).toString("base64url").replace(/-/g, ".");
  const up = { id: uploadId, key: req.key, initiated: now3(), fields, alg, ctype: alg ? ctype : "", owner: req.who || "anonymous" };
  writeJson(path.join(bucket.uploadDir(uploadId), "upload.json"), up);
  up.parts = new Map();
  bucket.uploads.set(uploadId, up);
  const inner = x("Bucket", bucket.name) + x("Key", req.key) + x("UploadId", uploadId);
  const headers = alg ? { "x-amz-checksum-algorithm": alg, "x-amz-checksum-type": ctype } : {};
  sseHeaders(fields.sse, headers);
  return xmlResponse("InitiateMultipartUploadResult", inner, 200, headers);
}

function getUpload(bucket, uploadId, key) {
  const up = bucket.uploads.get(uploadId);
  if (!up || up.key !== key) {
    throw new S3Error("NoSuchUpload", "The specified upload does not exist. The upload ID may be invalid, or the " +
      "upload may have been aborted or completed.", 404, { UploadId: uploadId });
  }
  return up;
}

async function uploadPart(req, bucket, uploadId) {
  let n;
  try {
    n = pyInt(req.q.partNumber || "");
  } catch {
    n = 0;
  }
  if (n < 1 || n > MAX_PARTS) {
    throw invalid("Part number must be an integer between 1 and 10000, inclusive", "partNumber", req.q.partNumber || "");
  }
  let up = getUpload(bucket, uploadId, req.key);
  const copy = req.headers["x-amz-copy-source"] !== undefined;
  let received;
  if (copy) {
    const [, , src, srcPath] = readSource(req.headers, req.who);
    const size = pyInt(src.size);
    let start = 0;
    let end = size - 1;
    const rng = req.headers["x-amz-copy-source-range"];
    if (rng) {
      const match = /^bytes=(\d+)-(\d+)$/.exec(pyStrip(rng));
      if (!match || Number(match[1]) > Number(match[2]) || Number(match[2]) >= size) {
        throw invalid("The x-amz-copy-source-range value must be of the form bytes=first-last where first " +
          "and last are the zero-based offsets of the first and last bytes to copy", "x-amz-copy-source-range", rng);
      }
      start = Number(match[1]);
      end = Number(match[2]);
    }
    received = await copyFile(srcPath, start, end, up.alg || "");
  } else {
    const [alg, expected] = wantedChecksum(req.headers);
    if (up.alg && alg && alg !== up.alg) {
      throw invalid(`Checksum Type mismatch occurred, expected checksum Type: ${up.alg.toLowerCase()}, actual ` +
        `checksum Type: ${alg.toLowerCase()}`, "x-amz-checksum-algorithm", alg);
    }
    received = await req.payload(up.alg || alg, expected);
  }
  const part = { n, size: received.size, etag: received.md5, time: now3() };
  if (received.checksum) part.checksum = received.checksum[1];
  try {
    up = getUpload(bucket, uploadId, req.key);
    fs.renameSync(received.path, path.join(bucket.uploadDir(uploadId), partName(n)));
    received.path = null;
    writeJson(path.join(bucket.uploadDir(uploadId), partJson(n)), part);
    up.parts.set(n, part);
  } finally {
    if (received.path) unlink(received.path);
  }
  const headers = {};
  if (part.checksum && up.alg) headers[checksumHeader(up.alg)] = part.checksum;
  if (copy) {
    let inner = x("LastModified", iso(part.time)) + x("ETag", `"${part.etag}"`);
    if (part.checksum && up.alg) inner += x(checksumElement(up.alg), part.checksum);
    return xmlResponse("CopyPartResult", inner, 200, headers);
  }
  headers.ETag = `"${part.etag}"`;
  sseHeaders(up.fields.sse, headers);
  return new Response(200, Buffer.alloc(0), headers);
}

async function completeUpload(req, bucket, uploadId) {
  const root = parseXml(await req.smallBody());
  if (root.tag !== "CompleteMultipartUpload") throw malformed();
  let up = getUpload(bucket, uploadId, req.key);
  const parts = new Map(up.parts);
  const alg = up.alg || "";
  const wanted = [];
  for (const el of root.findall("Part")) {
    let n;
    try {
      n = pyInt(text(el, "PartNumber"));
    } catch {
      throw malformed();
    }
    wanted.push([n, text(el, "ETag").replace(/^"+|"+$/g, ""), alg ? text(el, checksumElement(alg)) : ""]);
  }
  if (!wanted.length) throw malformed();
  const numbers = wanted.map((w) => w[0]);
  if (numbers.some((v, i) => i > 0 && v < numbers[i - 1]) || new Set(numbers).size !== numbers.length) {
    throw new S3Error("InvalidPartOrder", "The list of parts was not in ascending order. Parts must be ordered by part number.", 400,
      { UploadId: uploadId });
  }
  const chosen = [];
  wanted.forEach(([n, etag, cs], idx) => {
    const part = parts.get(n);
    if (!part || part.etag !== etag || (cs && part.checksum && cs !== part.checksum)) {
      throw new S3Error("InvalidPart", "One or more of the specified parts could not be found. The part may not have " +
        "been uploaded, or the specified entity tag may not match the part's entity tag.", 400,
      { UploadId: uploadId, PartNumber: String(n), ETag: etag });
    }
    if (idx < wanted.length - 1 && part.size < MIN_PART) {
      throw new S3Error("EntityTooSmall", "Your proposed upload is smaller than the minimum allowed object size.", 400, {
        ProposedSize: String(part.size), MinSizeAllowed: String(MIN_PART), PartNumber: String(n), ETag: etag,
      });
    }
    chosen.push(part);
  });
  if (req.headers["if-none-match"] === "*") {
    const rec = bucket.objects.get(req.key);
    if (rec && !rec.versions[0].dm) throw preconditionFailed("If-None-Match");
  }
  const full = alg && up.ctype === "FULL_OBJECT" ? newChecksum(alg) : null;
  const tmp = STORE.tempFile();
  let total = 0;
  const out = await fs.promises.open(tmp, "w");
  try {
    const buf = Buffer.alloc(1024 * 1024);
    for (const part of chosen) {
      const fin = await fs.promises.open(path.join(bucket.uploadDir(uploadId), partName(part.n)), "r");
      try {
        for (;;) {
          const { bytesRead } = await fin.read(buf, 0, buf.length, null);
          if (!bytesRead) break;
          const data = buf.subarray(0, bytesRead);
          if (full) full.update(data);
          await out.write(data);
          total += bytesRead;
        }
      } finally {
        await fin.close();
      }
    }
  } catch (err) {
    await out.close().catch(() => {});
    unlink(tmp);
    throw err;
  }
  await out.close();
  const etag = `${md5Hex(Buffer.concat(chosen.map((p) => Buffer.from(p.etag, "hex"))))}-${chosen.length}`;
  let checksum = null;
  if (alg) {
    if (full) {
      checksum = { alg, value: full.digest().toString("base64"), type: "FULL_OBJECT" };
    } else if (chosen.every((p) => p.checksum)) {
      const joined = Buffer.concat(chosen.map((p) => b64decodeLoose(p.checksum)));
      checksum = { alg, value: `${checksumOf(alg, joined)}-${chosen.length}`, type: "COMPOSITE" };
    }
    const sent = req.headers[checksumHeader(alg)];
    if (sent && checksum && sent !== checksum.value && sent !== checksum.value.split("-")[0]) {
      unlink(tmp);
      throw new S3Error("BadDigest", `The ${alg} you specified for the full object did not match the calculated checksum.`);
    }
  }
  let version;
  try {
    up = getUpload(bucket, uploadId, req.key);
    const blob = STORE.commitBlob(bucket, tmp);
    version = {
      ...up.fields,
      blob,
      size: total,
      etag,
      time: now3(),
      parts: chosen.map((p) => (p.checksum ? { size: p.size, etag: p.etag, checksum: p.checksum } : { size: p.size, etag: p.etag })),
    };
    if (checksum) version.checksum = checksum;
    version = putVersion(bucket, req.key, version);
    abortUpload(bucket, uploadId);
  } finally {
    if (fs.existsSync(tmp)) unlink(tmp);
  }
  const host = req.host || `127.0.0.1:${PORT}`;
  let inner = x("Location", `http://${host}/${bucket.name}/${quote(req.key)}`) + x("Bucket", bucket.name) + x("Key", req.key) +
    x("ETag", `"${etag}"`);
  if (checksum) inner += x(checksumElement(alg), checksum.value) + x("ChecksumType", checksum.type);
  const headers = {};
  if (bucket.meta.versioning) headers["x-amz-version-id"] = version.id;
  sseHeaders(version.sse, headers);
  return xmlResponse("CompleteMultipartUploadResult", inner, 200, headers);
}

function listParts(req, bucket, uploadId) {
  const up = getUpload(bucket, uploadId, req.key);
  const parts = [...up.parts.values()].sort((a, b) => a.n - b.n);
  const marker = pyInt(req.q["part-number-marker"] || "0");
  const maxParts = Math.min(pyInt(req.q["max-parts"] || "1000"), 1000);
  const after = parts.filter((p) => p.n > marker);
  const page = after.slice(0, Math.max(0, maxParts < 0 ? after.length + maxParts : maxParts));
  const truncated = after.length > maxParts;
  const alg = up.alg || "";
  let items = "";
  for (const p of page) {
    items += `<Part>${x("PartNumber", p.n)}${x("LastModified", iso(p.time))}${x("ETag", `"${p.etag}"`)}${x("Size", p.size)}`;
    if (alg && p.checksum) items += x(checksumElement(alg), p.checksum);
    items += "</Part>";
  }
  let inner = x("Bucket", bucket.name) + x("Key", req.key) + x("UploadId", uploadId) +
    `<Initiator>${x("ID", OWNER_ID)}${x("DisplayName", OWNER_NAME)}</Initiator>` + ownerXml() +
    x("StorageClass", g(up.fields, "class", "STANDARD")) + x("PartNumberMarker", marker) +
    x("NextPartNumberMarker", page.length ? page[page.length - 1].n : marker) + x("MaxParts", maxParts) +
    x("IsTruncated", truncated ? "true" : "false") + items;
  if (alg) inner += x("ChecksumAlgorithm", alg) + x("ChecksumType", up.ctype || "COMPOSITE");
  return xmlResponse("ListPartsResult", inner);
}

// ----------------------------------------------------------------------------- browser POST uploads

function splitBuffer(buf, sep) {
  const out = [];
  let start = 0;
  for (;;) {
    const idx = buf.indexOf(sep, start);
    if (idx < 0) break;
    out.push(buf.subarray(start, idx));
    start = idx + sep.length;
  }
  out.push(buf.subarray(start));
  return out;
}

function formFields(body, ctype) {
  const match = /boundary="?([^";]+)"?/.exec(ctype);
  if (!match) throw new S3Error("MalformedPOSTRequest", "The body of your POST request is not well-formed multipart/form-data.");
  const boundary = Buffer.from(`--${match[1]}`, "utf8");
  const fields = {};
  let filePart = null;
  for (let chunk of splitBuffer(body, boundary).slice(1)) {
    if (chunk.subarray(0, 2).toString("latin1") === "--") break;
    let s = 0;
    while (s < chunk.length && (chunk[s] === 13 || chunk[s] === 10)) s++;
    chunk = chunk.subarray(s);
    const sepAt = chunk.indexOf("\r\n\r\n");
    const head = sepAt < 0 ? chunk : chunk.subarray(0, sepAt);
    let data = sepAt < 0 ? Buffer.alloc(0) : chunk.subarray(sepAt + 4);
    if (data.length >= 2 && data[data.length - 2] === 13 && data[data.length - 1] === 10) data = data.subarray(0, data.length - 2);
    let disposition = "";
    let partType = "";
    for (const line of UTF8.decode(head).split("\r\n")) {
      const colon = line.indexOf(":");
      const name = pyStrip(colon < 0 ? line : line.slice(0, colon)).toLowerCase();
      const value = colon < 0 ? "" : line.slice(colon + 1);
      if (name === "content-disposition") disposition = value;
      else if (name === "content-type") partType = pyStrip(value);
    }
    const field = /name="([^"]*)"/.exec(disposition);
    if (!field) continue;
    const filename = /filename="([^"]*)"/.exec(disposition);
    if (field[1].toLowerCase() === "file") {
      filePart = [filename ? filename[1] : "", partType, data];
      break;
    }
    fields[field[1].toLowerCase()] = UTF8_STRICT.decode(data);
  }
  return [fields, filePart];
}

const signatureMismatch = () =>
  new S3Error("SignatureDoesNotMatch", "The request signature we calculated does not match the signature you provided.", 403);
const unknownKey = () => new S3Error("InvalidAccessKeyId", "The AWS Access Key Id you provided does not exist in our records.", 403);

async function postObject(req) {
  const bucket = STORE.get(req.bucket);
  const length = pyInt(req.headers["content-length"] || "0");
  if (length > MAX_POST) throw new S3Error("EntityTooLarge", "Your proposed upload exceeds the maximum allowed size", 400);
  const body = await req.smallBody(MAX_POST);
  const [fields, filePart] = formFields(body, req.headers["content-type"] || "");
  if (!filePart) throw invalid("POST requires exactly one file upload per request.", "file", "0");
  const [filename, partType, data] = filePart;
  let key = fields.key || "";
  if (!key) {
    throw invalid("Bucket POST must contain a field named 'key'.  If it is specified, please check the order of the fields.", "key", "");
  }
  key = key.split("${filename}").join(filename);
  if (AUTH === "off") {
    // anyone may post
  } else if (own(fields, "x-amz-signature") || own(fields, "signature")) {
    const policyB64 = fields.policy || "";
    if (!policyB64) throw invalid("Bucket POST must contain a field named 'policy'.", "policy", "");
    if (own(fields, "x-amz-signature")) {
      if (fields["x-amz-algorithm"] !== "AWS4-HMAC-SHA256") {
        throw invalid("Only AWS4-HMAC-SHA256 is supported.", "x-amz-algorithm", fields["x-amz-algorithm"] || "");
      }
      const parts = (fields["x-amz-credential"] || "").split("/");
      if (parts.length !== 5) throw invalid("The Credential is not valid.", "x-amz-credential", fields["x-amz-credential"] || "");
      if (!CREDENTIALS.has(parts[0])) throw unknownKey();
      const expected = crypto.createHmac("sha256", signingKey(CREDENTIALS.get(parts[0]), parts[1], parts[2], parts[3]))
        .update(policyB64, "utf8").digest("hex");
      if (!safeEqual(expected, fields["x-amz-signature"])) throw signatureMismatch();
    } else {
      const access = fields.awsaccesskeyid || "";
      if (!CREDENTIALS.has(access)) throw unknownKey();
      const expected = crypto.createHmac("sha1", Buffer.from(CREDENTIALS.get(access), "utf8")).update(policyB64, "utf8").digest("base64");
      if (!safeEqual(expected, fields.signature)) throw signatureMismatch();
    }
    checkPostPolicy(policyB64, fields, bucket.name, key, data.length);
  } else if (!anonymousAllowed(bucket, "s3:PutObject", key)) {
    throw denied();
  }
  const headers = nullObj();
  for (const [k, v] of Object.entries(fields)) {
    if (k.startsWith("x-amz-meta-") || STD_HEADERS.includes(k) ||
      ["x-amz-storage-class", "x-amz-server-side-encryption", "x-amz-website-redirect-location", "acl"].includes(k)) headers[k] = v;
  }
  if (headers.acl !== undefined) {
    headers["x-amz-acl"] = headers.acl;
    delete headers.acl;
  }
  headers["content-type"] = fields["content-type"] || partType || "binary/octet-stream";
  if (fields.tagging) {
    const tags = tagsFromXml(Buffer.from(fields.tagging, "utf8"));
    headers["x-amz-tagging"] = Object.entries(tags).map(([k, v]) => `${quote(k)}=${quote(v)}`).join("&");
  }
  const fieldsObj = objectFields(headers, bucket);
  const checksumFields = nullObj();
  for (const [k, v] of Object.entries(fields)) if (k.startsWith("x-amz-checksum-")) checksumFields[k] = v;
  const [alg, expectedCs] = wantedChecksum(checksumFields);
  const received = new Received();
  received.path = STORE.tempFile();
  fs.writeFileSync(received.path, data);
  received.size = data.length;
  received.md5 = md5Hex(data);
  if (alg) {
    received.checksum = [alg, checksumOf(alg, data)];
    if (expectedCs && expectedCs !== received.checksum[1]) {
      unlink(received.path);
      throw new S3Error("BadDigest", `The ${alg} you specified did not match the calculated checksum.`);
    }
  }
  const blob = STORE.commitBlob(bucket, received.path);
  const version = putVersion(bucket, key, newVersion(received, fieldsObj, blob));
  const etag = `"${version.etag}"`;
  const location = `http://${req.host}/${bucket.name}/${quote(key)}`;
  const outHeaders = { ETag: etag, Location: location };
  if (bucket.meta.versioning) outHeaders["x-amz-version-id"] = version.id;
  const redirect = fields.success_action_redirect || fields.redirect;
  if (redirect) {
    const sep = redirect.includes("?") ? "&" : "?";
    outHeaders.Location = `${redirect}${sep}bucket=${quote(bucket.name)}&key=${quote(key)}&etag=${quote(etag)}`;
    return new Response(303, Buffer.alloc(0), outHeaders);
  }
  const status = own(fields, "success_action_status") ? fields.success_action_status : "204";
  if (status === "201") {
    const inner = x("Location", location) + x("Bucket", bucket.name) + x("Key", key) + x("ETag", etag);
    return new Response(201, `<?xml version="1.0" encoding="UTF-8"?>\n<PostResponse>${inner}</PostResponse>`, outHeaders);
  }
  return new Response(status === "200" ? 200 : 204, Buffer.alloc(0), outHeaders);
}

function checkPostPolicy(policyB64, fields, bucket, key, size) {
  let policy;
  try {
    policy = JSON.parse(UTF8_STRICT.decode(b64decodeLoose(policyB64)));
  } catch {
    throw invalid("Invalid Policy: Invalid JSON.", "policy", "");
  }
  const expiration = parseTime(pyStr(pget(policy, "expiration", "")));
  if (expiration === null || expiration < epoch()) throw denied("Invalid according to Policy: Policy expired.");
  const values = { ...fields, bucket, key };
  const covered = new Set(["bucket"]);
  const conditions = pget(policy, "conditions");
  for (const cond of truthy(conditions) ? conditions : []) {
    if (isDict(cond)) {
      for (const [rawName, want] of Object.entries(cond)) {
        const name = rawName.toLowerCase();
        covered.add(name);
        if (pyStr(g(values, name, "")) !== pyStr(want)) {
          throw denied(`Invalid according to Policy: Policy Condition failed: ["eq", "$${name}", "${pyStr(want)}"]`);
        }
      }
    } else if (Array.isArray(cond) && cond.length === 3) {
      const op = pyStr(cond[0]).toLowerCase();
      if (op === "content-length-range") {
        if (!(pyInt(cond[1]) <= size && size <= pyInt(cond[2]))) {
          throw new S3Error(size > pyInt(cond[2]) ? "EntityTooLarge" : "EntityTooSmall",
            "Your proposed upload size does not match the policy's content-length-range.");
        }
        continue;
      }
      const name = pyStr(cond[1]).replace(/^\$+/, "").toLowerCase();
      covered.add(name);
      const value = pyStr(g(values, name, ""));
      if (op === "eq" && value !== pyStr(cond[2])) throw denied(`Invalid according to Policy: Policy Condition failed: ${pyDumps(cond)}`);
      if (op === "starts-with") {
        const prefixes = name === "content-type" ? pyStr(cond[2]).split(",").map((p) => pyStrip(p)) : [pyStr(cond[2])];
        if (!prefixes.some((p) => value.startsWith(p))) throw denied(`Invalid according to Policy: Policy Condition failed: ${pyDumps(cond)}`);
      }
    }
  }
  for (const name of Object.keys(fields)) {
    if (["policy", "x-amz-signature", "signature", "file", "awsaccesskeyid"].includes(name) || name.startsWith("x-ignore-")) continue;
    if (!covered.has(name)) throw denied(`Invalid according to Policy: Extra input fields: ${name}`);
  }
}

// ----------------------------------------------------------------------------- static website hosting

function webError(status, code, message) {
  const title = { 403: "403 Forbidden", 404: "404 Not Found" }[status] || String(status);
  const body = `<html><head><title>${title}</title></head><body><h1>${title}</h1><ul><li>Code: ${esc(code)}</li>` +
    `<li>Message: ${esc(message)}</li></ul></body></html>`;
  return new Response(status, body, {}, "text/html; charset=utf-8");
}

function website(req, bucketName, key, base) {
  if (req.method !== "GET" && req.method !== "HEAD") throw notAllowed();
  const bucket = STORE.buckets.get(bucketName);
  if (!bucket) return webError(404, "NoSuchBucket", `The specified bucket does not exist: ${bucketName}`);
  const raw = g(configsOf(bucket), "website");
  if (!raw) return webError(404, "NoSuchWebsiteConfiguration", "The specified bucket does not have a website configuration");
  const root = parseXml(Buffer.from(raw, "utf8"));
  const redirectAll = root.find("RedirectAllRequestsTo");
  if (redirectAll) {
    const proto = text(redirectAll, "Protocol") || "http";
    return new Response(301, Buffer.alloc(0), { Location: `${proto}://${text(redirectAll, "HostName")}/${quote(key)}` });
  }
  const suffix = text(root, "IndexDocument/Suffix");
  const errorDoc = text(root, "ErrorDocument/Key");
  const rules = root.findall("RoutingRules/RoutingRule");
  const redirectFor = (code) => {
    for (const rule of rules) {
      const cond = rule.find("Condition");
      if (cond) {
        const pfx = text(cond, "KeyPrefixEquals");
        const err = text(cond, "HttpErrorCodeReturnedEquals");
        if (pfx && !key.startsWith(pfx)) continue;
        if (err && String(code) !== err) continue;
        if (!err && code !== null) continue;
      } else if (code !== null) {
        continue;
      }
      const red = rule.find("Redirect");
      let newKey = key;
      if (text(red, "ReplaceKeyWith")) newKey = text(red, "ReplaceKeyWith");
      else if (red && red.find("ReplaceKeyPrefixWith") && cond) newKey = text(red, "ReplaceKeyPrefixWith") + key.slice(text(cond, "KeyPrefixEquals").length);
      const host = text(red, "HostName") || req.host;
      const proto = text(red, "Protocol") || "http";
      const status = pyInt(text(red, "HttpRedirectCode") || "301");
      return new Response(status, Buffer.alloc(0), { Location: `${proto}://${host}${!text(red, "HostName") ? base : "/"}${quote(newKey)}` });
    }
    return null;
  };
  const early = redirectFor(null);
  if (early) return early;
  const target = !key || key.endsWith("/") ? key + suffix : key;
  const fetch = (name) => {
    const rec = bucket.objects.get(name);
    if (!rec || rec.versions[0].dm) return null;
    return rec.versions[0];
  };
  const version = fetch(target);
  if (!version && key && !key.endsWith("/") && fetch(`${key}/${suffix}`)) {
    return new Response(302, Buffer.alloc(0), { Location: `${base}${quote(key)}/` });
  }
  const allowed = Boolean(version) && anonymousAllowed(bucket, "s3:GetObject", target, version);
  if (version && !allowed) return webError(403, "AccessDenied", "Access Denied");
  if (!version) {
    const red = redirectFor(404);
    if (red) return red;
    const errVersion = errorDoc ? fetch(errorDoc) : null;
    if (errVersion && anonymousAllowed(bucket, "s3:GetObject", errorDoc, errVersion)) {
      const type = errVersion.type || "text/html";
      return new Response(404, Buffer.alloc(0), { "Content-Type": type }, type, bucket.blobPath(errVersion.blob), 0, pyInt(errVersion.size));
    }
    return webError(404, "NoSuchKey", `The specified key does not exist. Key: ${target}`);
  }
  if (version.redirect) return new Response(301, Buffer.alloc(0), { Location: version.redirect });
  const headers = objectHeaders(version);
  return new Response(200, Buffer.alloc(0), headers, headers["Content-Type"], bucket.blobPath(version.blob), 0, pyInt(version.size));
}

// ----------------------------------------------------------------------------- web console API

const UI_READS = new Set(["ListBuckets", "ListObjects", "BucketInfo", "HeadObject", "ListVersions", "ListUploads", "Presign", "Stats"]);

async function uiRoute(req) {
  if (!UI_ON) throw new S3Error("NotFound", "The web console is off (S3_UI=off).", 404);
  const p = req.raw_path;
  if (p === "/ui") return new Response(302, Buffer.alloc(0), { Location: "/ui/" }, "text/plain");
  if (p === "/ui/" && (req.method === "GET" || req.method === "HEAD")) {
    return new Response(200, uiHtml(), UI_HEADERS, "text/html; charset=utf-8");
  }
  const found = sessionOf(req.headers.cookie || "");
  if (p === "/ui/session") {
    let data;
    if (AUTH === "off") {
      data = { authenticated: true, user: "", auth: false, csrf: "" };
    } else {
      data = {
        authenticated: Boolean(found),
        user: found ? found.user : "",
        auth: true,
        csrf: found ? found.csrf : "",
        password_login: Boolean(UI_PASSWORD),
      };
    }
    Object.assign(data, { region: REGION, version: VERSION });
    return jsonResponse(data);
  }
  if (p === "/ui/login" && req.method === "POST") {
    const ip = req.ip;
    const body = await req.smallBody(65536);
    if (AUTH === "off") return jsonResponse({ authenticated: true, csrf: "" }, {});
    if (throttled(ip)) throw new S3Error("SlowDown", "Too many failed sign-ins; wait 5 minutes.", 429);
    let data;
    try {
      data = JSON.parse(UTF8_STRICT.decode(body) || "{}");
    } catch {
      throw invalid("The request body is not valid JSON.");
    }
    const user = pyStr(pget(data, "user") || "");
    const password = pyStr(pget(data, "password") || "");
    if (!checkLogin(user, password)) {
      failed(ip);
      log("console sign-in refused from", ip);
      throw new S3Error("AccessDenied", "Wrong access key or password.", 401);
    }
    const [sid, csrf] = newSession(user || "console");
    log("console sign-in", user || "console", "from", ip);
    return jsonResponse({ authenticated: true, user, csrf }, {
      "Set-Cookie": `s3_session=${sid}; Path=/ui/; HttpOnly; SameSite=Strict; Max-Age=${SESSION_TTL}`,
      "Cache-Control": "no-store",
    });
  }
  if (p === "/ui/logout" && req.method === "POST") {
    if (found) SESSIONS.delete(found.id);
    return new Response(200, '{"authenticated": false}', { "Set-Cookie": "s3_session=; Path=/ui/; HttpOnly; Max-Age=0" }, "application/json");
  }
  if (AUTH !== "off" && !found) throw new S3Error("AccessDenied", "Sign in first.", 401);
  const user = found ? found.user : "";
  if (p === "/ui/download" && req.method === "GET") return uiDownload(req);
  if (AUTH !== "off" && !safeEqual(req.headers["x-s3-csrf"] || "", found ? found.csrf : "")) {
    throw new S3Error("AccessDenied", "The console's request token is missing; reload the page.", 403);
  }
  if (p === "/ui/upload" && req.method === "PUT") return uiUpload(req);
  if (p.startsWith("/ui/api/") && req.method === "POST") {
    let params;
    try {
      params = JSON.parse(UTF8_STRICT.decode(await req.smallBody()) || "{}");
    } catch {
      throw invalid("The request body is not valid JSON.");
    }
    const op = p.slice("/ui/api/".length);
    if (!own(UI_OPS, op)) throw new S3Error("NotImplemented", `Unknown console operation ${op}.`, 501);
    req.auth = new Auth(user || "console", "console");
    const result = await UI_OPS[op](params, req);
    if (!UI_READS.has(op)) log("console", op, pyStr(pget(params, "bucket", "")), pyStr(pget(params, "key", "")), "by", user || "console");
    return jsonResponse(result);
  }
  throw new S3Error("NotFound", "Not found.", 404);
}

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
  const out = [...STORE.buckets.keys()].sort(cmpStr).map((name) => {
    const b = STORE.buckets.get(name);
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
  const bucket = STORE.get(name);
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

function uiBucketInfo(p) {
  const bucket = STORE.get(param(p, "bucket"));
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
  };
}

function uiListObjects(p) {
  const bucket = STORE.get(param(p, "bucket"));
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
  const bucket = STORE.get(param(p, "bucket"));
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

function uiListVersions(p) {
  const bucket = STORE.get(param(p, "bucket"));
  const prefix = pyStr(pget(p, "prefix") || "");
  const out = [];
  for (const key of bucket.keys()) {
    if (!key.startsWith(prefix)) continue;
    const versions = bucket.objects.get(key).versions;
    for (let i = 0; i < versions.length; i++) {
      out.push(versionJson(key, versions[i], i === 0));
      if (out.length >= 2000) return { versions: out, truncated: true };
    }
  }
  return { versions: out, truncated: false };
}

function uiDeleteObjects(p) {
  const deleted = [];
  const errors = [];
  const bucket = STORE.get(param(p, "bucket"));
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
  const sb = STORE.get(srcBucket);
  const db = STORE.get(dstBucket);
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
    const blob = STORE.commitBlob(db, received.path);
    putVersion(db, dkey, newVersion(received, pick(src, FIELD_KEYS), blob));
    if (truthy(pget(p, "move"))) deleteObject(sb, skey, null, false);
    moved.push(dkey);
  }
  return { copied: moved };
}

function uiCreateFolder(p) {
  let key = param(p, "key");
  if (!key.endsWith("/")) key += "/";
  const bucket = STORE.get(param(p, "bucket"));
  const tmp = STORE.tempFile();
  fs.writeFileSync(tmp, Buffer.alloc(0));
  const received = new Received();
  received.path = tmp;
  received.md5 = md5Hex(Buffer.alloc(0));
  const blob = STORE.commitBlob(bucket, tmp);
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
  const bucket = STORE.get(param(p, "bucket"));
  const version = findVersion(bucket, param(p, "key"), optVid(p));
  version.tags = tags;
  bucket.saveRecord(param(p, "key"));
  return { tags };
}

/** Replace the content type, standard headers, user metadata and storage class (a copy onto itself). */
async function uiUpdateMeta(p) {
  const bucket = STORE.get(param(p, "bucket"));
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
  const blob = STORE.commitBlob(bucket, received.path);
  const version = putVersion(bucket, key, newVersion(received, fields, blob));
  return { versionId: version.id };
}

/** Make an older version the current one (copies it on top, like the AWS console). */
async function uiRestoreVersion(p) {
  const bucket = STORE.get(param(p, "bucket"));
  const key = param(p, "key");
  const src = { ...findVersion(bucket, key, param(p, "versionId")) };
  const received = await copyFile(bucket.blobPath(src.blob), 0, pyInt(src.size) - 1, truthy(src.checksum) ? g(src.checksum, "alg", "") : "");
  const blob = STORE.commitBlob(bucket, received.path);
  const version = putVersion(bucket, key, newVersion(received, pick(src, FIELD_KEYS), blob));
  return { versionId: version.id };
}

/** One bucket setting: versioning, tags, policy, acl, or a configuration document (XML, "" deletes it). */
function uiPutBucketSetting(p, req) {
  const name = param(p, "bucket");
  const setting = param(p, "setting");
  const value = pget(p, "value");
  const bucket = STORE.get(name);
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
  const bucket = STORE.get(param(p, "bucket"));
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
  const bucket = STORE.get(param(p, "bucket"));
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

function uiPresign(p, req) {
  const expires = pyInt(pget(p, "expires") || 3600);
  if (expires < 1 || expires > 604800) throw invalid("Expiry must be between 1 second and 7 days.");
  const access = CREDENTIALS.has(req.who) ? req.who : CREDENTIALS.keys().next().value || "";
  if (!access) throw invalid("Share links need a credential (S3_SECRET_ACCESS_KEY); authentication is off.");
  const method = pyStr(pget(p, "method") || "GET").toUpperCase();
  if (method !== "GET" && method !== "PUT") throw invalid("method must be GET or PUT");
  const host = pyStr(pget(p, "host") || req.host);
  const scheme = pyStr(pget(p, "scheme") || "") === "https" ? "https" : "http";
  return {
    url: presign(method, host, param(p, "bucket"), param(p, "key"), expires, access, pyStr(pget(p, "versionId") || ""), scheme),
    expires,
  };
}

function uiListUploads(p) {
  const bucket = STORE.get(param(p, "bucket"));
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
  const bucket = STORE.get(param(p, "bucket"));
  if (!bucket.uploads.has(param(p, "uploadId"))) throw new S3Error("NoSuchUpload", "The specified upload does not exist.", 404);
  abortUpload(bucket, param(p, "uploadId"));
  return { aborted: true };
}

function uiRestoreArchived(p) {
  const days = pyInt(pget(p, "days") || 1);
  const bucket = STORE.get(param(p, "bucket"));
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
  const bucket = STORE.get(bucketName);
  const headers = nullObj();
  headers["content-type"] = req.headers["content-type"] || "binary/octet-stream";
  if (req.q.class) headers["x-amz-storage-class"] = req.q.class;
  const fields = objectFields(headers, bucket);
  req.auth = new Auth("console", "console");
  req.auth.payload = "UNSIGNED-PAYLOAD";
  const received = await req.payload("", "");
  let version;
  try {
    const blob = STORE.commitBlob(bucket, received.path);
    received.path = null;
    version = putVersion(bucket, key, newVersion(received, fields, blob));
  } finally {
    if (received.path) unlink(received.path);
  }
  log("console upload", bucketName, key, received.size, "bytes");
  return jsonResponse({ key, etag: version.etag, versionId: version.id });
}

function uiDownload(req) {
  const bucket = STORE.get(req.q.bucket || "");
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

// ----------------------------------------------------------------------------- main

function check() {
  const host = BIND === "0.0.0.0" || !BIND ? "127.0.0.1" : BIND;
  const req = http.get({ host, port: PORT, path: "/-/health", timeout: 3000 }, (res) => process.exit(res.statusCode === 200 ? 0 : 1));
  req.on("timeout", () => process.exit(1));
  req.on("error", () => process.exit(1));
}

function main() {
  if (process.argv.slice(2).includes("--check")) return check();
  if (AUTH !== "sigv4" && AUTH !== "off") {
    console.error("S3_AUTH must be sigv4 or off");
    process.exit(2);
  }
  if (AUTH !== "off" && !CREDENTIALS.size) {
    console.error("set S3_SECRET_ACCESS_KEY (and S3_ACCESS_KEY_ID), or S3_CREDENTIALS=id:secret, or S3_AUTH=off");
    process.exit(2);
  }
  STORE = new Store(DATA_DIR);
  const server = http.createServer({ maxHeaderSize: 65536, requestTimeout: 0 }, (nreq, res) => {
    // A client that goes away mid-request is not an error worth a stack trace.
    nreq.on("error", () => {});
    res.on("error", () => {});
    dispatch(nreq, res).catch((err) => {
      log("error:", err && err.stack ? err.stack : String(err));
      res.destroy();
    });
  });
  server.on("clientError", (err, socket) => {
    if (err.code === "ECONNRESET" || !socket.writable) {
      socket.destroy();
      return;
    }
    socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
  });
  server.listen(PORT, BIND, () => {
    lifecycleLoop();
    log(`S3 compatible server ${VERSION} (Node.js) on ${BIND}:${PORT}, data ${DATA_DIR}, ${STORE.buckets.size} buckets, ` +
      `auth ${AUTH}${UI_ON ? ", console /ui/" : ""}`);
    if (AUTH === "off") log("warning: S3_AUTH=off, anyone who reaches the port can read and change every object");
  });
  process.on("SIGTERM", () => process.exit(0));
  process.on("SIGINT", () => process.exit(0));
  return undefined;
}

main();
