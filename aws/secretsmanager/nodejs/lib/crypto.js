"use strict";
// The ciphers of encryption at rest (Node's crypto), in the same format as the Python server:
// AES-256-GCM, ChaCha20-Poly1305 and AES-256-CBC + HMAC-SHA256 (encrypt-then-MAC, keys split with HKDF-SHA256).

const crypto = require("crypto");

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

module.exports = { DecryptError, gcmEncrypt, gcmDecrypt, ALGORITHMS, b64 };
