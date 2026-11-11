"use strict";
// Browser POST uploads (multipart/form-data with a signed POST policy, or anonymous when a policy or ACL allows).

const crypto = require("crypto");
const fs = require("fs");

const { g, isDict, nullObj, own, pget, pyDumps, pyInt, pyStr, pyStrip, truthy } = require("../py");
const { S3Error, denied, invalid } = require("../errors");
const { AUTH, CREDENTIALS, MAX_POST, STD_HEADERS } = require("../config");
const { UTF8, UTF8_STRICT, epoch, parseTime, quote, x } = require("../util");
const { b64decodeLoose, checksumOf, md5Hex, safeEqual } = require("../checksums");
const { getStore, unlink } = require("../store");
const { Auth, Received, signingKey, wantedChecksum } = require("../sigv4");
const { needAuth } = require("../access");
const { newVersion, objectFields, putVersion, tagsFromXml } = require("../versions");
const { Response } = require("../http");

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
  const bucket = getStore().get(req.bucket);
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
    req.auth = new Auth("anonymous", "off");
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
      req.auth = new Auth(parts[0], "sigv4");
    } else {
      const access = fields.awsaccesskeyid || "";
      if (!CREDENTIALS.has(access)) throw unknownKey();
      const expected = crypto.createHmac("sha1", Buffer.from(CREDENTIALS.get(access), "utf8")).update(policyB64, "utf8").digest("base64");
      if (!safeEqual(expected, fields.signature)) throw signatureMismatch();
      req.auth = new Auth(access, "sigv2");
    }
    req.auth.via = "POST";
    checkPostPolicy(policyB64, fields, bucket.name, key, data.length);
  }
  needAuth(req, bucket, "s3:PutObject", key);
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
  received.path = getStore().tempFile();
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
  const blob = getStore().commitBlob(bucket, received.path);
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

module.exports = { postObject };
