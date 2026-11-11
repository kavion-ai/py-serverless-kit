"use strict";
// The master keys and envelope encryption, the same format as the Python server: every secret version gets its own
// random 256-bit data key (DEK) that encrypts the value; the DEK is stored wrapped (AES-256-GCM) by a master key. The
// value's associated data is "ARN|VersionId", so a ciphertext can't be moved to another secret or version.

const crypto = require("crypto");
const { DecryptError, gcmEncrypt, gcmDecrypt, ALGORITHMS, b64 } = require("./crypto");
const { badRequest } = require("./errors");

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

module.exports = { Keyring, aadOf };
