"use strict";
// Multipart uploads: create, upload part (and part copy), complete (composite / full-object checksums), list parts.

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { g, pyInt, pyStrip } = require("../py");
const { S3Error, invalid, malformed, preconditionFailed } = require("../errors");
const { ALGORITHMS, MAX_PARTS, MIN_PART, OWNER_ID, OWNER_NAME, PORT } = require("../config");
const { iso, now3, ownerXml, parseXml, quote, text, x } = require("../util");
const { b64decodeLoose, checksumElement, checksumHeader, checksumOf, md5Hex, newChecksum } = require("../checksums");
const { getStore, partJson, partName, unlink, writeJson } = require("../store");
const { wantedChecksum } = require("../sigv4");
const { abortUpload, copyFile, objectFields, putVersion, readSource, sseHeaders } = require("../versions");
const { Response, xmlResponse } = require("../http");

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
    const [, , src, srcPath] = readSource(req);
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
  const tmp = getStore().tempFile();
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
    const blob = getStore().commitBlob(bucket, tmp);
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

module.exports = { createUpload, uploadPart, completeUpload, listParts };
