"use strict";
// The data on disk: Bucket (bucket.json, one record per key, blobs, uploads), Store (atomic JSON writes, the
// startup sweep) and the accessor every module reaches the open store through.

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { cmpStr, pyDumps, truthy } = require("./py");
const { noBucket } = require("./errors");
const { log } = require("./util");
const { sha256Hex } = require("./checksums");

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

let current = null;

/** The store main() opened. Every module reaches it through here, never through a copy. */
const getStore = () => current;

function setStore(store) {
  current = store;
}

const configsOf = (bucket) => (truthy(bucket.meta.configs) ? bucket.meta.configs : {});

module.exports = { Bucket, writeJson, unlink, rmTree, Store, partName, partJson, getStore, setStore, configsOf };
