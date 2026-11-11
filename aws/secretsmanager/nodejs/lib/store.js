"use strict";
// The store: every secret in memory (values in plain text) and in one JSON file (secretsmanager.json, mode 600,
// written atomically; values encrypted when the keyring has an algorithm). Same format as the Python server.

const fs = require("fs");
const { DATA_DIR, STORE_FILE } = require("./config");
const { DecryptError } = require("./crypto");
const { invalid, badRequest, notFound } = require("./errors");
const { aadOf } = require("./keyring");
const { log, has, sortKeys } = require("./util");

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

module.exports = { store };
