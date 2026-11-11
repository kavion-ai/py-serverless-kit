"use strict";
// Object lock: the bucket's default retention, and whether a version is protected (retention, legal hold).

const { g, pyInt, truthy } = require("./py");
const { S3Error, denied } = require("./errors");
const { epoch, parseXml, text } = require("./util");
const { configsOf } = require("./store");

function lockConfig(bucket) {
  const raw = g(configsOf(bucket), "object-lock", "");
  const out = { enabled: truthy(bucket.meta.object_lock), mode: "", days: 0, years: 0 };
  if (raw) {
    let root;
    try {
      root = parseXml(Buffer.from(raw, "utf8"));
    } catch (err) {
      if (err instanceof S3Error) return out;
      throw err;
    }
    out.enabled = out.enabled || text(root, "ObjectLockEnabled") === "Enabled";
    out.mode = text(root, "Rule/DefaultRetention/Mode");
    out.days = pyInt(text(root, "Rule/DefaultRetention/Days") || "0");
    out.years = pyInt(text(root, "Rule/DefaultRetention/Years") || "0");
  }
  return out;
}

function locked(version, now, bypass = false) {
  if (version.hold) return true;
  const retention = truthy(version.retention) ? version.retention : {};
  if (retention.until && retention.until > now) return !(retention.mode === "GOVERNANCE" && bypass);
  return false;
}

function checkUnlocked(version, bypass) {
  if (version.hold) throw denied("Access Denied because object protected by object lock.");
  if (locked(version, epoch(), bypass)) throw denied("Access Denied because object protected by object lock.");
}

module.exports = { lockConfig, locked, checkUnlocked };
