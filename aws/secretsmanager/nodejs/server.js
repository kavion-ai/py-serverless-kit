"use strict";
// An AWS Secrets Manager compatible server (Node.js, no dependencies).
//
// boto3, the AWS SDKs (JavaScript v3, Java, Go, ...), the AWS CLI and pskit's getSecret() talk to it unchanged:
// point their endpoint at this server and sign with an access key / secret key it knows. Requests are checked with
// AWS Signature Version 4, exactly as AWS does, so a wrong secret key is refused.
//
// A web console (/ui/) lists, creates, edits, versions, deletes and restores secrets. It signs in with the same
// access key and secret key (or SM_UI_PASSWORD) and keeps the session in an HttpOnly cookie.
//
// Settings (environment), the same as the Python server (../python/server.py):
//   SM_ACCESS_KEY_ID / SM_SECRET_ACCESS_KEY   the credentials clients sign with
//   SM_CREDENTIALS                            more credentials: id1:secret1,id2:secret2
//   SM_AUTH                                   sigv4 (default) or off (development only)
//   SM_PORT (4584), SM_BIND (0.0.0.0), SM_DATA_DIR (./data), SM_REGION (us-east-1), SM_ACCOUNT_ID (000000000000)
//   SM_UI (on), SM_UI_PASSWORD                the web console and an optional console password
//   SM_MASTER_KEY                             encrypts values at rest: 32 random bytes in base64, key id "default"
//   SM_MASTER_KEYS, SM_MASTER_KEY_ID          more master keys (id1:key,id2:key; KmsKeyId picks one) and the id
//                                             used for secrets without a KmsKeyId (changing it rewraps on start)
//   SM_ENCRYPTION                             aes-256-gcm (default with a key), chacha20-poly1305, aes-256-cbc-hmac, off
//
// The data is one JSON file (secretsmanager.json, mode 600) written atomically, in the same format as the Python
// server's; with a master key every version's value is stored encrypted with its own data key (envelope
// encryption). `node server.js --check` exits 0 when the server answers on /health (a container health check);
// `node server.js --rewrap` encrypts, decrypts or rewraps the file for the current settings and exits.

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
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
const UI_FILE = env.SM_UI_FILE || "";
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

function log(...parts) {
  console.log(new Date().toISOString().replace(/\.\d+Z$/, "+00:00"), ...parts);
}

class ApiError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

const notFound = () => new ApiError("ResourceNotFoundException", "Secrets Manager can't find the specified secret.");
const invalid = (message) => new ApiError("InvalidParameterException", message);
const badRequest = (message) => new ApiError("InvalidRequestException", message);
const now = () => Math.round(Date.now()) / 1000;
const today = () => Math.floor(Date.now() / 1000 / 86400) * 86400;
const has = (obj, key) => obj[key] !== undefined && obj[key] !== null;

// ----------------------------------------------------------------------------- encryption at rest
//
// Envelope encryption, the same format as the Python server: every secret version gets its own random 256-bit data
// key (DEK) that encrypts the value; the DEK is stored wrapped (AES-256-GCM) by a master key. The value's associated
// data is "ARN|VersionId", so a ciphertext can't be moved to another secret or version.

class DecryptError extends Error {}

function gcmEncrypt(name, key, iv, plain, aad) {
  const c = crypto.createCipheriv(name, key, iv, { authTagLength: 16 });
  c.setAAD(aad, { plaintextLength: plain.length });
  const ct = Buffer.concat([c.update(plain), c.final()]);
  return [ct, c.getAuthTag()];
}

function gcmDecrypt(name, key, iv, ct, tag, aad) {
  try {
    const d = crypto.createDecipheriv(name, key, iv, { authTagLength: 16 });
    d.setAAD(aad, { plaintextLength: ct.length });
    d.setAuthTag(tag);
    return Buffer.concat([d.update(ct), d.final()]);
  } catch (_err) {
    throw new DecryptError(`${name} tag mismatch`);
  }
}

function cbcKeys(dek) {
  const hkdf = (info) => Buffer.from(crypto.hkdfSync("sha256", dek, Buffer.alloc(0), Buffer.from(info), 32));
  return [hkdf("pskit-sm aes-256-cbc enc"), hkdf("pskit-sm hmac-sha256 mac")];
}

function cbcMac(macKey, aad, iv, ct) {
  const len = Buffer.alloc(8);
  len.writeBigUInt64BE(BigInt(aad.length));
  return crypto.createHmac("sha256", macKey).update(Buffer.concat([len, aad, iv, ct])).digest();
}

// name -> [SM_ENCRYPTION value, nonce bytes, encrypt, decrypt]
const ALGORITHMS = {
  "AES-256-GCM": ["aes-256-gcm", 12, (k, iv, p, a) => gcmEncrypt("aes-256-gcm", k, iv, p, a),
    (k, iv, c, t, a) => gcmDecrypt("aes-256-gcm", k, iv, c, t, a)],
  "ChaCha20-Poly1305": ["chacha20-poly1305", 12, (k, iv, p, a) => gcmEncrypt("chacha20-poly1305", k, iv, p, a),
    (k, iv, c, t, a) => gcmDecrypt("chacha20-poly1305", k, iv, c, t, a)],
  "AES-256-CBC-HMAC-SHA256": ["aes-256-cbc-hmac", 16, (dek, iv, plain, aad) => {
    const [encKey, macKey] = cbcKeys(dek);
    const c = crypto.createCipheriv("aes-256-cbc", encKey, iv);
    const ct = Buffer.concat([c.update(plain), c.final()]);
    return [ct, cbcMac(macKey, aad, iv, ct)];
  }, (dek, iv, ct, tag, aad) => {
    const [encKey, macKey] = cbcKeys(dek);
    const want = cbcMac(macKey, aad, iv, ct);
    if (tag.length !== want.length || !crypto.timingSafeEqual(want, tag)) throw new DecryptError("AES-CBC HMAC-SHA256 tag mismatch");
    try {
      const d = crypto.createDecipheriv("aes-256-cbc", encKey, iv);
      return Buffer.concat([d.update(ct), d.final()]);
    } catch (_err) {
      throw new DecryptError("AES-CBC padding is not valid");
    }
  }],
};
const b64 = (buf) => Buffer.from(buf).toString("base64");

// The master keys (SM_MASTER_KEY is key id "default", SM_MASTER_KEYS=id:key,... adds more), the algorithm new
// versions are encrypted with (SM_ENCRYPTION) and the key id they are wrapped with (SM_MASTER_KEY_ID).
class Keyring {
  constructor(e) {
    const masterKey = (name, value) => {
      const text = String(value).trim();
      const raw = /^[A-Za-z0-9+/]*={0,2}$/.test(text) && text.length % 4 === 0 ? Buffer.from(text, "base64") : Buffer.alloc(0);
      if (raw.length !== 32) throw new Error(`${name} must be 32 random bytes in base64 (openssl rand -base64 32)`);
      return raw;
    };
    this.keys = {};
    if (e.SM_MASTER_KEY) this.keys.default = masterKey("SM_MASTER_KEY", e.SM_MASTER_KEY);
    for (const pair of (e.SM_MASTER_KEYS || "").split(",")) {
      if (!pair.trim()) continue;
      const at = pair.indexOf(":");
      const kid = pair.slice(0, at).trim();
      const value = pair.slice(at + 1).trim();
      if (at < 0 || !kid || !value) throw new Error("SM_MASTER_KEYS must be id1:base64key,id2:base64key");
      this.keys[kid] = masterKey(`SM_MASTER_KEYS (${kid})`, value);
    }
    const ids = Object.keys(this.keys).sort();
    this.current = (e.SM_MASTER_KEY_ID || "").trim() || (this.keys.default ? "default" : ids[0] || "default");
    const mode = (e.SM_ENCRYPTION || "").trim().toLowerCase();
    const names = {};
    for (const [alg, spec] of Object.entries(ALGORITHMS)) names[spec[0]] = alg;
    if (mode && mode !== "off" && !names[mode]) throw new Error(`SM_ENCRYPTION must be one of ${Object.keys(names).join(", ")} or off`);
    this.alg = mode === "off" || (!mode && !ids.length) ? "" : names[mode || "aes-256-gcm"];
    if (this.alg && !ids.length) throw new Error(`SM_ENCRYPTION=${mode} needs a master key: set SM_MASTER_KEY (32 bytes, base64)`);
    if (this.alg && !this.keys[this.current]) throw new Error(`SM_MASTER_KEY_ID '${this.current}' is not in SM_MASTER_KEY / SM_MASTER_KEYS`);
  }

  // The master key id a secret's KmsKeyId names (an id, alias/<id>, or a KMS ARN ending in one).
  keyId(kmsKeyId, strict = false) {
    if (!kmsKeyId) return this.current;
    let name = String(kmsKeyId).split(":").pop();
    for (const prefix of ["alias/", "key/"]) if (name.startsWith(prefix)) name = name.slice(prefix.length);
    if (name === "aws/secretsmanager") return this.current;
    if (Object.prototype.hasOwnProperty.call(this.keys, name)) return name;
    if (strict && this.alg) {
      throw badRequest(`KmsKeyId ${kmsKeyId} is not a master key of this server (known: ${Object.keys(this.keys).sort().join(", ")}).`);
    }
    return this.current;
  }

  wrap(dek, kid, aad) {
    const iv = crypto.randomBytes(12);
    const [ct, tag] = gcmEncrypt("aes-256-gcm", this.keys[kid], iv, dek, Buffer.concat([aad, Buffer.from(`|${kid}`)]));
    return { kid, dek: b64(Buffer.concat([ct, tag])), dek_iv: b64(iv) };
  }

  unwrap(rec, aad) {
    const kid = String(rec.kid);
    if (!Object.prototype.hasOwnProperty.call(this.keys, kid)) throw new DecryptError(`master key '${kid}' is not set (SM_MASTER_KEY / SM_MASTER_KEYS)`);
    const blob = Buffer.from(rec.dek, "base64");
    try {
      return gcmDecrypt("aes-256-gcm", this.keys[kid], Buffer.from(rec.dek_iv, "base64"), blob.subarray(0, -16),
        blob.subarray(-16), Buffer.concat([aad, Buffer.from(`|${kid}`)]));
    } catch (_err) {
      throw new DecryptError(`master key '${kid}' does not open the data key (wrong key?)`);
    }
  }

  seal(field, plain, aad, kid) {
    const [, size, encrypt] = ALGORITHMS[this.alg];
    const dek = crypto.randomBytes(32);
    const iv = crypto.randomBytes(size);
    const [ct, tag] = encrypt(dek, iv, plain, aad);
    return { alg: this.alg, field, iv: b64(iv), ct: b64(ct), tag: b64(tag), ...this.wrap(dek, kid, aad) };
  }

  open(rec, aad) {
    if (!ALGORITHMS[rec.alg]) throw new DecryptError(`unknown algorithm '${rec.alg}'`);
    const dek = this.unwrap(rec, aad);
    try {
      return ALGORITHMS[rec.alg][3](dek, Buffer.from(rec.iv, "base64"), Buffer.from(rec.ct, "base64"),
        Buffer.from(rec.tag, "base64"), aad);
    } catch (_err) {
      throw new DecryptError("the value's tag does not match (the data was changed)");
    }
  }

  // The same ciphertext with its data key wrapped by master key `kid`.
  rewrap(rec, aad, kid) {
    return { ...rec, ...this.wrap(this.unwrap(rec, aad), kid, aad) };
  }
}

const aadOf = (secret, vid) => Buffer.from(`${secret.ARN}|${vid}`, "utf8");

// ----------------------------------------------------------------------------- store

const store = {
  secrets: {},
  keyring: null,
  // "ARN\nVersionId" -> the version's Encrypted record. Versions never change, so each is sealed once.
  sealed: new Map(),
  load(keyring) {
    this.keyring = keyring;
    if (fs.existsSync(STORE_FILE)) {
      const text = fs.readFileSync(STORE_FILE, "utf8");
      const data = text.trim() ? JSON.parse(text) : {};
      for (const s of data.secrets || []) this.secrets[s.Name] = s;
      for (const secret of Object.values(this.secrets)) {
        for (const [vid, version] of Object.entries(secret.Versions)) {
          const rec = version.Encrypted;
          if (!rec) continue;
          delete version.Encrypted;
          let plain;
          try {
            plain = keyring.open(rec, aadOf(secret, vid));
          } catch (err) {
            throw new DecryptError(`can't decrypt secret '${secret.Name}' version ${vid}: ${err.message}`);
          }
          version[rec.field] = rec.field === "SecretString" ? plain.toString("utf8") : plain.toString("base64");
          this.sealed.set(`${secret.ARN}\n${vid}`, rec);
        }
      }
    }
  },
  // The file doesn't match the settings: plain values to encrypt (or the reverse), or data keys to rewrap.
  stale() {
    for (const secret of Object.values(this.secrets)) {
      const kid = this.keyring.keyId(secret.KmsKeyId);
      for (const vid of Object.keys(secret.Versions)) {
        const rec = this.sealed.get(`${secret.ARN}\n${vid}`);
        if (Boolean(rec) !== Boolean(this.keyring.alg) || (rec && rec.kid !== kid)) return true;
      }
    }
    return false;
  },
  onDisk(secret) {
    if (!this.keyring.alg) return secret;
    const kid = this.keyring.keyId(secret.KmsKeyId);
    const versions = {};
    for (const [vid, version] of Object.entries(secret.Versions)) {
      const key = `${secret.ARN}\n${vid}`;
      const aad = aadOf(secret, vid);
      let rec = this.sealed.get(key);
      if (!rec) {
        const field = has(version, "SecretString") ? "SecretString" : "SecretBinary";
        const plain = field === "SecretString" ? Buffer.from(version[field], "utf8") : Buffer.from(version[field], "base64");
        rec = this.keyring.seal(field, plain, aad, kid);
      } else if (rec.kid !== kid) {
        rec = this.keyring.rewrap(rec, aad, kid);
      }
      this.sealed.set(key, rec);
      const rest = {};
      for (const [k, v] of Object.entries(version)) if (k !== "SecretString" && k !== "SecretBinary") rest[k] = v;
      versions[vid] = { ...rest, Encrypted: rec };
    }
    return { ...secret, Versions: versions };
  },
  save() {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    const tmp = `${STORE_FILE}.tmp`;
    const names = Object.keys(this.secrets).sort();
    const written = names.map((n) => sortKeys(this.onDisk(this.secrets[n])));
    const live = new Set();
    for (const s of Object.values(this.secrets)) for (const vid of Object.keys(s.Versions)) live.add(`${s.ARN}\n${vid}`);
    for (const key of [...this.sealed.keys()]) if (!live.has(key) || !this.keyring.alg) this.sealed.delete(key);
    const payload = { format: this.keyring.alg ? 2 : 1, secrets: written };
    const fd = fs.openSync(tmp, "w", 0o600);
    try {
      fs.writeSync(fd, JSON.stringify(sortKeys(payload), null, 1));
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    fs.renameSync(tmp, STORE_FILE);
  },
  purge() {
    const t = Date.now() / 1000;
    const gone = Object.keys(this.secrets).filter((n) => this.secrets[n].DeletionDate && this.secrets[n].DeletionDate <= t);
    for (const name of gone) {
      delete this.secrets[name];
      log("purged", name);
    }
    if (gone.length) this.save();
  },
  find(id) {
    if (typeof id !== "string" || !id) throw invalid("SecretId is required.");
    if (Object.prototype.hasOwnProperty.call(this.secrets, id)) return this.secrets[id];
    for (const secret of Object.values(this.secrets)) {
      const arn = secret.ARN;
      // A full ARN, or a partial one without the 6-character suffix AWS adds to the name.
      if (id === arn || (arn.length === id.length + 7 && arn.startsWith(`${id}-`))) return secret;
    }
    throw notFound();
  },
  live(id) {
    const secret = this.find(id);
    if (secret.DeletedDate) throw badRequest("You can't perform this operation on the secret because it was marked for deletion.");
    return secret;
  },
};

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = sortKeys(value[key]);
    return out;
  }
  return value;
}

// ----------------------------------------------------------------------------- helpers

function requestToken(p) {
  if (!has(p, "ClientRequestToken")) return crypto.randomUUID();
  const token = p.ClientRequestToken;
  if (typeof token !== "string" || token.length < 32 || token.length > 64) throw invalid("ClientRequestToken must be 32-64 characters.");
  return token;
}

function secretValue(p, required = false) {
  const text = p.SecretString;
  const blob = p.SecretBinary;
  if (has(p, "SecretString") && has(p, "SecretBinary")) {
    throw invalid("You can't specify both a binary secret value and a string secret value in the same secret.");
  }
  if (has(p, "SecretString")) {
    if (typeof text !== "string" || Buffer.byteLength(text, "utf8") > MAX_VALUE) {
      throw invalid(`SecretString must be a string of at most ${MAX_VALUE} bytes.`);
    }
    return { SecretString: text };
  }
  if (has(p, "SecretBinary")) {
    const str = String(blob);
    if (!/^[A-Za-z0-9+/]*={0,2}$/.test(str) || str.length % 4 !== 0) throw invalid("SecretBinary must be base64.");
    const raw = Buffer.from(str, "base64");
    if (raw.length > MAX_VALUE) throw invalid(`SecretBinary must be at most ${MAX_VALUE} bytes.`);
    return { SecretBinary: raw.toString("base64") };
  }
  if (required) throw invalid("You must provide either SecretString or SecretBinary.");
  return null;
}

function parseTags(raw) {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) throw invalid("Tags must be a list of {Key, Value}.");
  return raw.map((tag) => {
    if (!tag || typeof tag.Key !== "string" || tag.Key.length < 1 || tag.Key.length > 128) {
      throw invalid("Each tag needs a Key of 1-128 characters.");
    }
    return { Key: tag.Key, Value: String(tag.Value || "") };
  });
}

function mergeTags(old, add) {
  const merged = new Map(old.map((t) => [t.Key, t.Value]));
  for (const t of add) merged.set(t.Key, t.Value);
  return [...merged].map(([Key, Value]) => ({ Key, Value }));
}

function stagesOf(secret) {
  const out = {};
  for (const [vid, v] of Object.entries(secret.Versions)) if (v.Stages.length) out[vid] = [...v.Stages];
  return out;
}

const sameValue = (version, value) =>
  (version.SecretString === undefined ? null : version.SecretString) === (value.SecretString === undefined ? null : value.SecretString) &&
  (version.SecretBinary === undefined ? null : version.SecretBinary) === (value.SecretBinary === undefined ? null : value.SecretBinary);

const drop = (list, item) => {
  const at = list.indexOf(item);
  if (at >= 0) list.splice(at, 1);
};

/** Attach `stage` to version `to` only. Moving AWSCURRENT gives the old current version AWSPREVIOUS. */
function moveStage(secret, stage, to) {
  const versions = secret.Versions;
  for (const [vid, version] of Object.entries(versions)) {
    if (vid !== to && version.Stages.includes(stage)) {
      drop(version.Stages, stage);
      if (stage === "AWSCURRENT") {
        for (const other of Object.values(versions)) drop(other.Stages, "AWSPREVIOUS");
        version.Stages.push("AWSPREVIOUS");
      }
    }
  }
  if (!versions[to].Stages.includes(stage)) versions[to].Stages.push(stage);
}

function prune(secret) {
  const versions = secret.Versions;
  const ids = Object.keys(versions);
  if (ids.length <= MAX_VERSIONS) return;
  const old = ids.filter((vid) => !versions[vid].Stages.length).sort((a, b) => versions[a].CreatedDate - versions[b].CreatedDate);
  for (const vid of old.slice(0, ids.length - MAX_VERSIONS)) delete versions[vid];
}

/** A new version of `secret` (idempotent for the same token and value). Returns its stages. */
function addVersion(secret, token, value, stages) {
  if (Object.prototype.hasOwnProperty.call(secret.Versions, token)) {
    const existing = secret.Versions[token];
    if (!sameValue(existing, value)) {
      throw new ApiError("ResourceExistsException", "You can't modify an existing version, you can only create a new version.");
    }
    return [...existing.Stages];
  }
  if (stages === undefined || stages === null) stages = ["AWSCURRENT"];
  if (!Array.isArray(stages) || !stages.every((s) => typeof s === "string" && s.length >= 1 && s.length <= 256)) {
    throw invalid("VersionStages must be a list of staging labels.");
  }
  secret.Versions[token] = { ...value, CreatedDate: now(), Stages: [] };
  for (const stage of new Set(stages)) moveStage(secret, stage, token);
  secret.LastChangedDate = now();
  prune(secret);
  return [...secret.Versions[token].Stages];
}

function pickVersion(secret, p) {
  const versions = secret.Versions;
  if (p.VersionId) {
    const version = versions[p.VersionId];
    if (!version || (p.VersionStage && !version.Stages.includes(p.VersionStage))) {
      throw new ApiError("ResourceNotFoundException", `Secrets Manager can't find the specified secret value for VersionId: ${p.VersionId}`);
    }
    return [p.VersionId, version];
  }
  const stage = p.VersionStage || "AWSCURRENT";
  for (const [vid, version] of Object.entries(versions)) if (version.Stages.includes(stage)) return [vid, version];
  throw new ApiError("ResourceNotFoundException", `Secrets Manager can't find the specified secret value for staging label: ${stage}`);
}

function valueOut(secret, vid, version) {
  const out = { ARN: secret.ARN, Name: secret.Name, VersionId: vid, VersionStages: [...version.Stages], CreatedDate: version.CreatedDate };
  for (const field of ["SecretString", "SecretBinary"]) if (version[field] !== undefined) out[field] = version[field];
  return out;
}

function describe(secret, listShape = false) {
  const out = { ARN: secret.ARN, Name: secret.Name, RotationEnabled: false, CreatedDate: secret.CreatedDate, LastChangedDate: secret.LastChangedDate };
  for (const field of ["Description", "KmsKeyId", "LastAccessedDate", "DeletedDate"]) if (has(secret, field)) out[field] = secret[field];
  if (secret.Tags && secret.Tags.length) out.Tags = secret.Tags.map((t) => ({ ...t }));
  out[listShape ? "SecretVersionsToStages" : "VersionIdsToStages"] = stagesOf(secret);
  return out;
}

function page(p, items, limitDefault = 100) {
  const limit = Number(p.MaxResults || limitDefault);
  if (!Number.isInteger(limit)) throw invalid("MaxResults must be a number.");
  if (limit < 1 || limit > 100) throw invalid("MaxResults must be between 1 and 100.");
  let start = 0;
  if (p.NextToken) {
    start = Number(Buffer.from(String(p.NextToken), "base64").toString("ascii"));
    if (!Number.isInteger(start) || start < 0) throw invalid("NextToken is not valid.");
  }
  const more = start + limit < items.length;
  return [items.slice(start, start + limit), more ? Buffer.from(String(start + limit)).toString("base64") : null];
}

/** ListSecrets filters: every filter must match; a value is a case-insensitive prefix, `!` in front negates. */
function matches(secret, filters) {
  if (!filters || (Array.isArray(filters) && !filters.length)) return true;
  if (!Array.isArray(filters)) throw invalid("Filters must be a list of {Key, Values}.");
  const tags = secret.Tags || [];
  const fields = {
    name: [secret.Name],
    description: [secret.Description || ""],
    "tag-key": tags.map((t) => t.Key),
    "tag-value": tags.map((t) => t.Value),
    "primary-region": [],
    "owning-service": [],
  };
  for (const flt of filters) {
    const key = (flt || {}).Key;
    let candidates;
    if (key === "all") candidates = [...fields.name, ...fields.description, ...fields["tag-key"], ...fields["tag-value"]];
    else if (Object.prototype.hasOwnProperty.call(fields, key)) candidates = fields[key];
    else throw invalid(`Filter key '${key}' is not valid.`);
    const hit = ((flt || {}).Values || []).some((value) => {
      let text = String(value);
      const negate = text.startsWith("!");
      if (negate) text = text.slice(1);
      const found = candidates.some((c) => c.toLowerCase().startsWith(text.toLowerCase()));
      return found !== negate;
    });
    if (!hit) return false;
  }
  return true;
}

const sortedSecrets = () => Object.keys(store.secrets).sort(byCodePoint).map((n) => store.secrets[n]);

function byCodePoint(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

function randomFrom(chars) {
  return chars[crypto.randomInt(chars.length)];
}

// ----------------------------------------------------------------------------- operations

const OPERATIONS = {
  CreateSecret(p, region) {
    const name = p.Name;
    if (typeof name !== "string" || !NAME_RE.test(name)) throw invalid("Name must be 1-512 characters of letters, digits and /_+=.@-");
    const value = secretValue(p);
    const token = requestToken(p);
    const existing = store.secrets[name];
    if (existing) {
      if (existing.DeletedDate) {
        throw badRequest("You can't create this secret because a secret with this name is already scheduled for deletion.");
      }
      const version = existing.Versions[token];
      if (value && version && sameValue(version, value)) return { ARN: existing.ARN, Name: name, VersionId: token };
      throw new ApiError("ResourceExistsException", `The operation failed because the secret ${name} already exists.`);
    }
    const alnum = LOWER + UPPER + DIGITS;
    let suffix = "";
    for (let i = 0; i < 6; i += 1) suffix += randomFrom(alnum);
    const t = now();
    const secret = {
      Name: name,
      ARN: `arn:aws:secretsmanager:${region}:${ACCOUNT}:secret:${name}-${suffix}`,
      CreatedDate: t,
      LastChangedDate: t,
      Tags: parseTags(p.Tags),
      Versions: {},
    };
    if (has(p, "Description")) secret.Description = String(p.Description);
    if (p.KmsKeyId) {
      store.keyring.keyId(p.KmsKeyId, true);
      secret.KmsKeyId = String(p.KmsKeyId);
    }
    const out = { ARN: secret.ARN, Name: name };
    if (value) {
      addVersion(secret, token, value, null);
      out.VersionId = token;
    }
    store.secrets[name] = secret;
    store.save();
    return out;
  },

  GetSecretValue(p) {
    const secret = store.live(p.SecretId);
    const [vid, version] = pickVersion(secret, p);
    if (secret.LastAccessedDate !== today()) {
      secret.LastAccessedDate = today();
      store.save();
    }
    return valueOut(secret, vid, version);
  },

  BatchGetSecretValue(p, region) {
    const ids = p.SecretIdList;
    const filters = p.Filters;
    if (ids && ids.length && filters && filters.length) throw invalid("Use either SecretIdList or Filters, not both.");
    const values = [];
    const errors = [];
    const one = (sid) => {
      try {
        values.push(OPERATIONS.GetSecretValue({ SecretId: sid }, region));
      } catch (err) {
        if (!(err instanceof ApiError)) throw err;
        errors.push({ SecretId: sid, ErrorCode: err.code, Message: err.message });
      }
    };
    if (ids && ids.length) {
      if (!Array.isArray(ids) || ids.length > 20) throw invalid("SecretIdList holds 1-20 secret ids.");
      ids.forEach(one);
      return { SecretValues: values, Errors: errors };
    }
    const matched = sortedSecrets().filter((s) => !s.DeletedDate && matches(s, filters));
    const [chunk, next] = page(p, matched, 20);
    for (const secret of chunk) one(secret.Name);
    const out = { SecretValues: values, Errors: errors };
    if (next) out.NextToken = next;
    return out;
  },

  PutSecretValue(p) {
    const secret = store.live(p.SecretId);
    const value = secretValue(p, true);
    const token = requestToken(p);
    const stages = addVersion(secret, token, value, p.VersionStages);
    store.save();
    return { ARN: secret.ARN, Name: secret.Name, VersionId: token, VersionStages: stages };
  },

  UpdateSecret(p) {
    const secret = store.live(p.SecretId);
    const value = secretValue(p);
    if (p.KmsKeyId) store.keyring.keyId(p.KmsKeyId, true);
    const out = { ARN: secret.ARN, Name: secret.Name };
    if (has(p, "Description")) secret.Description = String(p.Description);
    if (p.KmsKeyId) secret.KmsKeyId = String(p.KmsKeyId);
    if (value) {
      const token = requestToken(p);
      addVersion(secret, token, value, null);
      out.VersionId = token;
    }
    secret.LastChangedDate = now();
    store.save();
    return out;
  },

  DescribeSecret(p) {
    return describe(store.find(p.SecretId));
  },

  ListSecrets(p) {
    const items = sortedSecrets().filter((s) => (p.IncludePlannedDeletion || !s.DeletedDate) && matches(s, p.Filters));
    if (p.SortOrder === "desc") items.reverse();
    else if (has(p, "SortOrder") && p.SortOrder !== "asc") throw invalid("SortOrder must be asc or desc.");
    const [chunk, next] = page(p, items);
    const out = { SecretList: chunk.map((s) => describe(s, true)) };
    if (next) out.NextToken = next;
    return out;
  },

  DeleteSecret(p) {
    const secret = store.find(p.SecretId);
    const force = Boolean(p.ForceDeleteWithoutRecovery);
    if (force && has(p, "RecoveryWindowInDays")) {
      throw invalid("You can't use ForceDeleteWithoutRecovery in conjunction with RecoveryWindowInDays.");
    }
    const out = { ARN: secret.ARN, Name: secret.Name };
    if (force) {
      delete store.secrets[secret.Name];
      out.DeletionDate = now();
    } else {
      if (secret.DeletedDate) {
        throw badRequest("You can't perform this operation on the secret because it was already scheduled for deletion.");
      }
      const days = Number(has(p, "RecoveryWindowInDays") ? p.RecoveryWindowInDays : 30);
      if (!Number.isInteger(days)) throw invalid("RecoveryWindowInDays must be a number.");
      if (days < 7 || days > 30) throw invalid("RecoveryWindowInDays must be between 7 and 30 days.");
      secret.DeletedDate = now();
      secret.DeletionDate = Math.round(Date.now() + days * 86400 * 1000) / 1000;
      out.DeletionDate = secret.DeletionDate;
    }
    store.save();
    return out;
  },

  RestoreSecret(p) {
    const secret = store.find(p.SecretId);
    delete secret.DeletedDate;
    delete secret.DeletionDate;
    store.save();
    return { ARN: secret.ARN, Name: secret.Name };
  },

  ListSecretVersionIds(p) {
    const secret = store.find(p.SecretId);
    let versions = Object.entries(secret.Versions).sort((a, b) => b[1].CreatedDate - a[1].CreatedDate);
    if (!p.IncludeDeprecated) versions = versions.filter(([, v]) => v.Stages.length);
    const rows = versions.map(([vid, v]) => ({ VersionId: vid, VersionStages: [...v.Stages], CreatedDate: v.CreatedDate }));
    const [chunk, next] = page(p, rows);
    const out = { ARN: secret.ARN, Name: secret.Name, Versions: chunk };
    if (next) out.NextToken = next;
    return out;
  },

  UpdateSecretVersionStage(p) {
    const secret = store.live(p.SecretId);
    const stage = p.VersionStage;
    if (typeof stage !== "string" || !stage) throw invalid("VersionStage is required.");
    const removeFrom = p.RemoveFromVersionId;
    const moveTo = p.MoveToVersionId;
    const versions = secret.Versions;
    const holder = Object.keys(versions).find((vid) => versions[vid].Stages.includes(stage));
    if (holder && moveTo && holder !== moveTo && removeFrom !== holder) {
      throw invalid(`The staging label ${stage} is currently attached to version ${holder}, so you must explicitly reference that version in RemoveFromVersionId.`);
    }
    for (const vid of [removeFrom, moveTo]) if (vid && !versions[vid]) throw invalid(`Version ${vid} does not exist.`);
    if (moveTo) moveStage(secret, stage, moveTo);
    else if (removeFrom) {
      if (stage === "AWSCURRENT") throw invalid("You can't remove AWSCURRENT; move it to another version instead.");
      drop(versions[removeFrom].Stages, stage);
    }
    secret.LastChangedDate = now();
    store.save();
    return { ARN: secret.ARN, Name: secret.Name };
  },

  TagResource(p) {
    const secret = store.find(p.SecretId);
    secret.Tags = mergeTags(secret.Tags || [], parseTags(p.Tags));
    store.save();
    return {};
  },

  UntagResource(p) {
    const secret = store.find(p.SecretId);
    const keys = p.TagKeys || [];
    if (!Array.isArray(keys)) throw invalid("TagKeys must be a list.");
    secret.Tags = (secret.Tags || []).filter((t) => !keys.includes(t.Key));
    store.save();
    return {};
  },

  GetRandomPassword(p) {
    const length = Number(p.PasswordLength || 32);
    if (!Number.isInteger(length)) throw invalid("PasswordLength must be a number.");
    if (length < 1 || length > 4096) throw invalid("PasswordLength must be between 1 and 4096.");
    const exclude = String(p.ExcludeCharacters || "");
    let groups = [];
    if (!p.ExcludeLowercase) groups.push(LOWER);
    if (!p.ExcludeUppercase) groups.push(UPPER);
    if (!p.ExcludeNumbers) groups.push(DIGITS);
    if (!p.ExcludePunctuation) groups.push(PUNCTUATION);
    if (p.IncludeSpace) groups.push(" ");
    groups = groups.map((g) => [...g].filter((c) => !exclude.includes(c)).join("")).filter(Boolean);
    if (!groups.length) throw invalid("The password has no characters left to use.");
    const every = has(p, "RequireEachIncludedType") ? Boolean(p.RequireEachIncludedType) : true;
    if (every && length < groups.length) throw invalid("PasswordLength is too short to include every character type.");
    const pool = groups.join("");
    const chars = every ? groups.map(randomFrom) : [];
    while (chars.length < length) chars.push(randomFrom(pool));
    for (let i = chars.length - 1; i > 0; i -= 1) {
      const j = crypto.randomInt(i + 1);
      [chars[i], chars[j]] = [chars[j], chars[i]];
    }
    return { RandomPassword: chars.join("") };
  },

  PutResourcePolicy(p) {
    const secret = store.live(p.SecretId);
    try {
      JSON.parse(String(p.ResourcePolicy));
    } catch {
      throw new ApiError("MalformedPolicyDocumentException", "ResourcePolicy must be a JSON policy document.");
    }
    secret.ResourcePolicy = String(p.ResourcePolicy);
    store.save();
    return { ARN: secret.ARN, Name: secret.Name };
  },

  GetResourcePolicy(p) {
    const secret = store.find(p.SecretId);
    const out = { ARN: secret.ARN, Name: secret.Name };
    if (secret.ResourcePolicy) out.ResourcePolicy = secret.ResourcePolicy;
    return out;
  },

  DeleteResourcePolicy(p) {
    const secret = store.find(p.SecretId);
    delete secret.ResourcePolicy;
    store.save();
    return { ARN: secret.ARN, Name: secret.Name };
  },

  ValidateResourcePolicy(p) {
    try {
      JSON.parse(String(p.ResourcePolicy));
    } catch {
      throw new ApiError("MalformedPolicyDocumentException", "ResourcePolicy must be a JSON policy document.");
    }
    return { PolicyValidationPassed: true, ValidationErrors: [] };
  },
};

for (const name of ["RotateSecret", "CancelRotateSecret", "ReplicateSecretToRegions", "RemoveRegionsFromReplication", "StopReplicationToReplica"]) {
  OPERATIONS[name] = () => {
    throw badRequest(`${name} is not supported by this Secrets Manager compatible server (no rotation functions or replica regions).`);
  };
}

// Operations that change nothing: they are not logged.
const READS = new Set(["GetSecretValue", "BatchGetSecretValue", "DescribeSecret", "ListSecrets", "ListSecretVersionIds",
  "GetRandomPassword", "GetResourcePolicy", "ValidateResourcePolicy"]);

function run(operation, params, region, who) {
  if (!Object.prototype.hasOwnProperty.call(OPERATIONS, operation)) {
    throw new ApiError("UnknownOperationException", `Operation ${operation} is not known.`);
  }
  if (!params || typeof params !== "object" || Array.isArray(params)) {
    throw new ApiError("SerializationException", "The request body must be a JSON object.");
  }
  // Node runs one request at a time here (every operation is synchronous), so no lock is needed.
  store.purge();
  const out = OPERATIONS[operation](params, region);
  if (!READS.has(operation)) log(operation, params.SecretId || params.Name || "", "by", who);
  return out;
}

// ----------------------------------------------------------------------------- signature version 4

/** RFC 3986 encoding, as Python's urllib.parse.quote(safe="-_.~"). */
function uriEncode(text) {
  return encodeURIComponent(text).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

function parseQuery(query) {
  const pairs = [];
  for (const part of query.split(/[&;]/)) {
    if (!part) continue;
    const at = part.indexOf("=");
    const raw = (s) => decodeURIComponent(s.replace(/\+/g, " "));
    pairs.push(at < 0 ? [raw(part), ""] : [raw(part.slice(0, at)), raw(part.slice(at + 1))]);
  }
  return pairs;
}

const hmac = (key, text) => crypto.createHmac("sha256", key).update(text, "utf8").digest();
const sha256 = (data) => crypto.createHash("sha256").update(data).digest("hex");

function safeEqual(a, b) {
  const x = Buffer.from(String(a), "utf8");
  const y = Buffer.from(String(b), "utf8");
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

/** [access key id, region] of a correctly signed request, else an ApiError as AWS answers it. */
function verifySigv4(method, pathname, query, headers, body) {
  const auth = headers.authorization || "";
  if (!auth) throw new ApiError("MissingAuthenticationTokenException", "Missing Authentication Token");
  const match = AUTH_RE.exec(auth.trim());
  if (!match) {
    throw new ApiError("IncompleteSignatureException", "Authorization header requires Credential, SignedHeaders and Signature (AWS4-HMAC-SHA256).");
  }
  const [, credential, signedHeaders, signature] = match;
  const parts = credential.split("/");
  if (parts.length !== 5 || parts[4] !== "aws4_request") throw new ApiError("IncompleteSignatureException", "The Credential is not valid.");
  const [accessKey, day, region, service] = parts;
  if (!Object.prototype.hasOwnProperty.call(CREDENTIALS, accessKey)) {
    throw new ApiError("UnrecognizedClientException", "The security token included in the request is invalid.");
  }
  const secret = CREDENTIALS[accessKey];
  const amzDate = headers["x-amz-date"] || "";
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(amzDate);
  if (!m) throw new ApiError("IncompleteSignatureException", "X-Amz-Date is missing or not valid.");
  const when = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) / 1000;
  if (Math.abs(Date.now() / 1000 - when) > SKEW) {
    throw new ApiError("InvalidSignatureException", `Signature expired: ${amzDate} is now earlier or later than 15 minutes from the server's time.`);
  }
  if (day !== amzDate.slice(0, 8) || service !== "secretsmanager") {
    throw new ApiError("InvalidSignatureException", "The credential scope does not match the request.");
  }
  const names = signedHeaders.split(";");
  if (!names.includes("host") || names.some((n) => headers[n] === undefined)) {
    throw new ApiError("InvalidSignatureException", "SignedHeaders must include host and only headers that were sent.");
  }
  const payloadHash = sha256(body);
  const claimed = headers["x-amz-content-sha256"];
  if (claimed && claimed !== payloadHash) throw new ApiError("InvalidSignatureException", "x-amz-content-sha256 does not match the request body.");
  const pairs = parseQuery(query).map(([k, v]) => [uriEncode(k), uriEncode(v)]);
  pairs.sort((a, b) => byCodePoint(a[0], b[0]) || byCodePoint(a[1], b[1]));
  const canonical = [
    method.toUpperCase(),
    pathname || "/",
    pairs.map(([k, v]) => `${k}=${v}`).join("&"),
    names.map((n) => `${n}:${String(headers[n]).trim().split(/\s+/).join(" ")}\n`).join(""),
    signedHeaders,
    payloadHash,
  ].join("\n");
  const scope = `${day}/${region}/${service}/aws4_request`;
  const toSign = ["AWS4-HMAC-SHA256", amzDate, scope, sha256(canonical)].join("\n");
  let key = Buffer.from(`AWS4${secret}`, "utf8");
  for (const part of [day, region, service, "aws4_request"]) key = hmac(key, part);
  const expected = crypto.createHmac("sha256", key).update(toSign, "utf8").digest("hex");
  if (!safeEqual(expected, signature)) {
    throw new ApiError("InvalidSignatureException", "The request signature we calculated does not match the signature you provided. Check your AWS Secret Access Key and signing method.");
  }
  return [accessKey, region];
}

// ----------------------------------------------------------------------------- web console sessions

const sessions = new Map();
const failures = new Map();

function checkLogin(user, password) {
  if (UI_PASSWORD) return safeEqual(password, UI_PASSWORD);
  const known = Object.prototype.hasOwnProperty.call(CREDENTIALS, user);
  // Compare against a dummy for an unknown user, so the time is the same.
  return safeEqual(password, known ? CREDENTIALS[user] : "\0".repeat(32)) && known;
}

function throttled(ip) {
  const t = Date.now() / 1000;
  const recent = (failures.get(ip) || []).filter((x) => t - x < 300);
  failures.set(ip, recent);
  return recent.length >= 10;
}

function failed(ip) {
  failures.set(ip, [...(failures.get(ip) || []), Date.now() / 1000]);
}

function newSession(user) {
  const sid = crypto.randomBytes(32).toString("base64url");
  const csrf = crypto.randomBytes(24).toString("base64url");
  const t = Date.now() / 1000;
  for (const [key, s] of sessions) if (s.expires < t) sessions.delete(key);
  sessions.set(sid, { user, csrf, expires: t + SESSION_TTL });
  return [sid, csrf];
}

function sessionOf(cookieHeader) {
  for (const part of String(cookieHeader || "").split(";")) {
    const at = part.indexOf("=");
    if (at > 0 && part.slice(0, at).trim() === "sm_session") {
      const id = part.slice(at + 1).trim();
      const found = sessions.get(id);
      if (found && found.expires > Date.now() / 1000) return { ...found, id };
    }
  }
  return null;
}

function uiHtml() {
  const candidates = [UI_FILE, path.join(__dirname, "index.html"), path.join(__dirname, "..", "ui", "index.html")].filter(Boolean);
  for (const file of candidates) if (fs.existsSync(file)) return fs.readFileSync(file);
  return Buffer.from("<!doctype html><title>Secrets console</title><p>The console page (index.html) is missing.");
}

// ----------------------------------------------------------------------------- HTTP

const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; frame-ancestors 'none'; form-action 'self'";

function send(res, status, body, ctype, extra = {}) {
  const data = Buffer.isBuffer(body) ? body : Buffer.from(body);
  res.writeHead(status, {
    "Content-Type": ctype,
    "Content-Length": data.length,
    "x-amzn-RequestId": crypto.randomUUID(),
    Server: `pskit-secretsmanager/${VERSION}`,
    ...extra,
  });
  res.end(res.req.method === "HEAD" ? undefined : data);
}

const sendJson = (res, status, data, extra) => send(res, status, JSON.stringify(data), "application/x-amz-json-1.1", extra);

function sendError(res, err, ui = false) {
  sendJson(res, err.status, { __type: err.code, message: err.message }, ui ? {} : { "x-amzn-ErrorType": err.code });
}

function params(body) {
  let data;
  try {
    data = body.toString("utf8").trim() ? JSON.parse(body.toString("utf8")) : {};
  } catch {
    throw new ApiError("SerializationException", "The request body is not valid JSON.");
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new ApiError("SerializationException", "The request body must be a JSON object.");
  return data;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(new ApiError("SerializationException", "The request body is too large.", 413));
        req.destroy();
      } else chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function headerMap(req) {
  // Node joins repeated headers with ", "; AWS's canonical form joins them with ",".
  const out = {};
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    const name = req.rawHeaders[i].toLowerCase();
    const value = req.rawHeaders[i + 1].trim();
    out[name] = out[name] === undefined ? value : `${out[name]},${value}`;
  }
  return out;
}

function handleGet(req, res, pathname) {
  if (pathname === "/health" || pathname === "/healthz") {
    return send(res, 200, JSON.stringify({ status: "ok", secrets: Object.keys(store.secrets).length, version: VERSION }), "application/json");
  }
  if (UI_ON && (pathname === "/" || pathname === "/ui")) return send(res, 302, "", "text/plain", { Location: "/ui/" });
  if (UI_ON && pathname === "/ui/") {
    return send(res, 200, uiHtml(), "text/html; charset=utf-8", {
      "Cache-Control": "no-store",
      "X-Frame-Options": "DENY",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Content-Security-Policy": CSP,
    });
  }
  if (UI_ON && pathname === "/ui/session") {
    const found = sessionOf(req.headers.cookie);
    const data = AUTH === "off"
      ? { authenticated: true, user: "", auth: false, csrf: "" }
      : { authenticated: Boolean(found), user: found ? found.user : "", auth: true, csrf: found ? found.csrf : "", password_login: Boolean(UI_PASSWORD) };
    return send(res, 200, JSON.stringify(data), "application/json", { "Cache-Control": "no-store" });
  }
  return sendError(res, new ApiError("NotFound", "Not found. The Secrets Manager API takes POST / with X-Amz-Target.", 404));
}

function handleUi(req, res, pathname, body) {
  const ip = req.socket.remoteAddress || "";
  if (pathname === "/ui/login") {
    if (AUTH === "off") return sendJson(res, 200, { authenticated: true, csrf: "" });
    if (throttled(ip)) throw new ApiError("ThrottlingException", "Too many failed sign-ins; wait 5 minutes.", 429);
    const data = params(body);
    const user = String(data.user || "");
    const password = String(data.password || "");
    if (!checkLogin(user, password)) {
      failed(ip);
      log("console sign-in refused from", ip);
      throw new ApiError("AccessDeniedException", "Wrong access key or password.", 401);
    }
    const [sid, csrf] = newSession(user || "console");
    log("console sign-in", user || "console", "from", ip);
    return sendJson(res, 200, { authenticated: true, user, csrf }, {
      "Set-Cookie": `sm_session=${sid}; Path=/ui/; HttpOnly; SameSite=Strict; Max-Age=${SESSION_TTL}`,
      "Cache-Control": "no-store",
    });
  }
  const found = sessionOf(req.headers.cookie);
  if (pathname === "/ui/logout") {
    if (found) sessions.delete(found.id);
    return sendJson(res, 200, { authenticated: false }, { "Set-Cookie": "sm_session=; Path=/ui/; HttpOnly; Max-Age=0" });
  }
  if (!pathname.startsWith("/ui/api/")) throw new ApiError("NotFound", "Not found.", 404);
  if (AUTH !== "off") {
    if (!found) throw new ApiError("AccessDeniedException", "Sign in first.", 401);
    if (!safeEqual(req.headers["x-sm-csrf"] || "", found.csrf)) {
      throw new ApiError("AccessDeniedException", "The console's request token is missing; reload the page.", 403);
    }
  }
  const who = found ? `console:${found.user}` : "console";
  return sendJson(res, 200, run(pathname.slice("/ui/api/".length), params(body), REGION, who), { "Cache-Control": "no-store" });
}

async function handle(req, res) {
  const url = new URL(req.url, "http://localhost");
  const rawPath = req.url.split("?")[0];
  const query = req.url.includes("?") ? req.url.slice(req.url.indexOf("?") + 1) : "";
  try {
    if (req.method === "GET" || req.method === "HEAD") return handleGet(req, res, url.pathname);
    if (req.method !== "POST") throw new ApiError("NotFound", "Not found.", 404);
    const body = await readBody(req);
    if (url.pathname.startsWith("/ui/")) {
      if (!UI_ON) throw new ApiError("NotFound", "The web console is off (SM_UI=off).", 404);
      return handleUi(req, res, url.pathname, body);
    }
    const headers = headerMap(req);
    const target = headers["x-amz-target"] || "";
    const dot = target.indexOf(".");
    const service = dot < 0 ? target : target.slice(0, dot);
    const operation = dot < 0 ? "" : target.slice(dot + 1);
    if (service !== "secretsmanager" || !operation) throw new ApiError("UnknownOperationException", "X-Amz-Target must be secretsmanager.<Operation>.");
    let who = "anonymous";
    let region = REGION;
    if (AUTH !== "off") [who, region] = verifySigv4("POST", rawPath, query, headers, body);
    return sendJson(res, 200, run(operation, params(body), region, who));
  } catch (err) {
    if (err instanceof ApiError) return sendError(res, err, url.pathname.startsWith("/ui/"));
    log("error:", err && err.stack ? err.stack : String(err));
    return sendError(res, new ApiError("InternalServiceError", "The server failed to process the request.", 500));
  }
}

function check() {
  const host = BIND === "0.0.0.0" || !BIND ? "127.0.0.1" : BIND;
  const req = http.get({ host, port: PORT, path: "/health", timeout: 3000 }, (res) => process.exit(res.statusCode === 200 ? 0 : 1));
  req.on("timeout", () => process.exit(1));
  req.on("error", () => process.exit(1));
}

function main() {
  if (process.argv.includes("--check")) return check();
  if (AUTH !== "sigv4" && AUTH !== "off") {
    console.error("SM_AUTH must be sigv4 or off");
    process.exit(2);
  }
  const rewrapOnly = process.argv.includes("--rewrap");
  if (AUTH !== "off" && !Object.keys(CREDENTIALS).length && !rewrapOnly) {
    console.error("set SM_SECRET_ACCESS_KEY (and SM_ACCESS_KEY_ID), or SM_CREDENTIALS=id:secret, or SM_AUTH=off");
    process.exit(2);
  }
  try {
    store.load(new Keyring(env));
  } catch (err) {
    console.error(`secretsmanager: ${err.message}`);
    process.exit(2);
  }
  // Encrypt a plain file, decrypt it with SM_ENCRYPTION=off, or rewrap the data keys to the current master key.
  if (store.stale()) store.save();
  const keyring = store.keyring;
  if (rewrapOnly) {
    log(keyring.alg ? `rewrapped ${STORE_FILE} to master key '${keyring.current}'` : `wrote ${STORE_FILE} unencrypted`);
    return;
  }
  const server = http.createServer((req, res) => {
    handle(req, res);
  });
  server.listen(PORT, BIND, () => {
    log(`Secrets Manager compatible server ${VERSION} (Node.js) on ${BIND}:${PORT}, data ${STORE_FILE}, ${Object.keys(store.secrets).length} secrets, auth ${AUTH}${UI_ON ? ", console /ui/" : ""}${keyring.alg ? `, encryption ${keyring.alg} (master key '${keyring.current}')` : ", not encrypted"}`);
    if (AUTH === "off") log("warning: SM_AUTH=off, anyone who reaches the port can read every secret");
    if (!keyring.alg) log("warning: secrets are stored unencrypted; set SM_MASTER_KEY (openssl rand -base64 32) to encrypt them");
  });
  const stop = () => server.close(() => process.exit(0));
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}

main();
