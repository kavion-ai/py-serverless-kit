"use strict";
// Settings from the environment (S3_*), constants and the credentials clients sign with.

const crypto = require("crypto");
const path = require("path");

const { pyFloat, pyInt, pyStrip } = require("./py");

const VERSION = "1.0.0";
const env = process.env;
const PORT = pyInt(env.S3_PORT || "9000");
const BIND = env.S3_BIND || "0.0.0.0";
const DATA_DIR = env.S3_DATA_DIR ? path.normalize(env.S3_DATA_DIR).replace(/(.)[\\/]+$/, "$1") : path.join(process.cwd(), "data");
const REGION = env.S3_REGION || "us-east-1";
const ACCOUNT = env.S3_ACCOUNT_ID || "000000000000";
const AUTH = (env.S3_AUTH || "sigv4").toLowerCase();
const DOMAINS = (env.S3_DOMAIN || "localhost").split(",").map((d) => pyStrip(d).toLowerCase()).filter(Boolean);
const UI_ON = !["off", "0", "false", "no"].includes((env.S3_UI || "on").toLowerCase());
const UI_PASSWORD = env.S3_UI_PASSWORD || "";
const MAX_OBJECT = pyInt(env.S3_MAX_OBJECT_SIZE || String(5 * 1024 ** 3));
const MIN_PART = pyInt(env.S3_MIN_PART_SIZE || String(5 * 1024 ** 2));
const LIFECYCLE_INTERVAL = pyFloat(env.S3_LIFECYCLE_INTERVAL || "3600");
const DAY = pyFloat(env.S3_LIFECYCLE_DAY_SECONDS || "86400");
const UI_DIR = env.S3_UI_DIR || "";
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

/** access key id -> secret. A Map keeps the order credentials were given in (the console's share links use the first). */
function credentialsFromEnv() {
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

module.exports = {
  VERSION, PORT, BIND, DATA_DIR, REGION, ACCOUNT, AUTH, DOMAINS, UI_ON, UI_PASSWORD, UI_DIR, MAX_OBJECT, MIN_PART,
  LIFECYCLE_INTERVAL, DAY, MAX_XML, MAX_POST, MAX_PARTS, SKEW, SESSION_TTL, OWNER_ID, OWNER_NAME, NS, ALL_USERS,
  AUTH_USERS, LOG_DELIVERY, STORAGE_CLASSES, ARCHIVED, CANNED, STD_HEADERS, ALGORITHMS, CREDENTIALS,
};
