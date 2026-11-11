"use strict";
// CRC32 / CRC32C / CRC64NVME / SHA checksums, MD5 / SHA-256 / HMAC helpers and base64 decoding as Python does it.

const crypto = require("crypto");
const zlib = require("zlib");

const { ValueError } = require("./py");
const { invalid } = require("./errors");

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

module.exports = {
  newChecksum, checksumOf, checksumHeader, checksumElement, md5Hex, sha256Hex, hmacSha256, safeEqual, b64decodeStrict,
  b64decodeLoose,
};
