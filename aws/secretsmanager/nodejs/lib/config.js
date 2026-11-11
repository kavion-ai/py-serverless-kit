"use strict";
// Settings from the environment, limits and constants shared by every module.

const path = require("path");

const VERSION = "1.0.0";
const env = process.env;
const PORT = Number(env.SM_PORT || 4584);
const BIND = env.SM_BIND || "0.0.0.0";
const DATA_DIR = env.SM_DATA_DIR || path.join(process.cwd(), "data");
const STORE_FILE = path.join(DATA_DIR, "secretsmanager.json");
const REGION = env.SM_REGION || "us-east-1";
const ACCOUNT = env.SM_ACCOUNT_ID || "000000000000";
const AUTH = (env.SM_AUTH || "sigv4").toLowerCase();
const UI_ON = !["off", "0", "false", "no"].includes((env.SM_UI || "on").toLowerCase());
const UI_PASSWORD = env.SM_UI_PASSWORD || "";
const UI_DIR = env.SM_UI_DIR || "";
const MAX_BODY = 1024 * 1024;
const MAX_VALUE = 65536;
const MAX_VERSIONS = 100;
const SKEW = 15 * 60;
const SESSION_TTL = 12 * 3600;
const LOWER = "abcdefghijklmnopqrstuvwxyz";
const UPPER = LOWER.toUpperCase();
const DIGITS = "0123456789";
const PUNCTUATION = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~";
const NAME_RE = /^[A-Za-z0-9/_+=.@-]{1,512}$/;
const AUTH_RE = /^AWS4-HMAC-SHA256\s+Credential=([^,\s]+),\s*SignedHeaders=([^,\s]+),\s*Signature=([0-9a-f]{64})$/;

function credentialsFromEnv() {
  const out = {};
  if (env.SM_SECRET_ACCESS_KEY) out[env.SM_ACCESS_KEY_ID || "pskit"] = env.SM_SECRET_ACCESS_KEY;
  for (const pair of (env.SM_CREDENTIALS || "").split(",")) {
    const at = pair.indexOf(":");
    const key = pair.slice(0, at).trim();
    const secret = pair.slice(at + 1).trim();
    if (at > 0 && key && secret) out[key] = secret;
  }
  return out;
}

const CREDENTIALS = credentialsFromEnv();

module.exports = {
  VERSION, env, PORT, BIND, DATA_DIR, STORE_FILE, REGION, ACCOUNT, AUTH, UI_ON, UI_PASSWORD, UI_DIR, MAX_BODY,
  MAX_VALUE, MAX_VERSIONS, SKEW, SESSION_TTL, LOWER, UPPER, DIGITS, PUNCTUATION, NAME_RE, AUTH_RE, CREDENTIALS,
};
