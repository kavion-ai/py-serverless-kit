"use strict";
// Lifecycle rules: parsing, and the sweep that expires, transitions and cleans up (every S3_LIFECYCLE_INTERVAL).

const { g, own, pyInt, truthy } = require("./py");
const { S3Error, invalid, malformed } = require("./errors");
const { DAY, LIFECYCLE_INTERVAL } = require("./config");
const { epoch, log, parseTime, parseXml, text } = require("./util");
const { configsOf, getStore } = require("./store");
const { locked } = require("./objectlock");
const { abortUpload, deleteObject, removeVersion } = require("./versions");

function lifecycleRules(bucket) {
  if (own(bucket.parsed, "lifecycle")) return bucket.parsed.lifecycle;
  let rules = [];
  const raw = g(configsOf(bucket), "lifecycle");
  if (raw) {
    try {
      rules = parseLifecycle(Buffer.from(raw, "utf8"));
    } catch (err) {
      if (!(err instanceof S3Error)) throw err;
      rules = [];
    }
  }
  bucket.parsed.lifecycle = rules;
  return rules;
}

function num(value) {
  if (!value) return null;
  try {
    return pyInt(value);
  } catch {
    throw malformed();
  }
}

function parseLifecycle(body) {
  const root = parseXml(body);
  if (root.tag !== "LifecycleConfiguration") throw malformed();
  const rules = [];
  for (const rule of root.findall("Rule")) {
    const status = text(rule, "Status");
    if (status !== "Enabled" && status !== "Disabled") throw malformed();
    const flt = rule.find("Filter");
    let prefix = text(rule, "Prefix");
    const tags = {};
    let gt = null;
    let lt = null;
    if (flt) {
      const scope = flt.find("And") || flt;
      prefix = text(scope, "Prefix", prefix);
      for (const tag of scope.findall("Tag")) tags[text(tag, "Key")] = text(tag, "Value");
      gt = num(text(scope, "ObjectSizeGreaterThan"));
      lt = num(text(scope, "ObjectSizeLessThan"));
    }
    const exp = rule.find("Expiration");
    const nce = rule.find("NoncurrentVersionExpiration");
    const abort = rule.find("AbortIncompleteMultipartUpload");
    const transitions = rule.findall("Transition").map((tr) => ({
      days: num(text(tr, "Days")),
      date: parseTime(text(tr, "Date")),
      class: text(tr, "StorageClass"),
    }));
    const ncTransitions = rule.findall("NoncurrentVersionTransition").map((tr) => ({
      days: num(text(tr, "NoncurrentDays")),
      class: text(tr, "StorageClass"),
    }));
    const item = {
      id: text(rule, "ID"),
      enabled: status === "Enabled",
      prefix,
      tags,
      gt,
      lt,
      exp_days: num(text(exp, "Days")),
      exp_date: parseTime(text(exp, "Date")),
      exp_marker: text(exp, "ExpiredObjectDeleteMarker").toLowerCase() === "true",
      nc_days: num(text(nce, "NoncurrentDays")),
      nc_keep: num(text(nce, "NewerNoncurrentVersions")),
      abort_days: num(text(abort, "DaysAfterInitiation")),
      transitions,
      nc_transitions: ncTransitions,
    };
    if (item.exp_days !== null && item.exp_days < 1) throw invalid("'Days' for Expiration action must be a positive integer");
    rules.push(item);
  }
  if (!rules.length || rules.length > 1000) throw malformed();
  return rules;
}

function ruleMatches(rule, key, version) {
  if (!rule.enabled || !key.startsWith(rule.prefix)) return false;
  const tags = truthy(version.tags) ? version.tags : {};
  if (Object.entries(rule.tags).some(([k, v]) => g(tags, k) !== v)) return false;
  const size = pyInt(version.size || 0);
  if (rule.gt !== null && !(size > rule.gt)) return false;
  return !(rule.lt !== null && !(size < rule.lt));
}

/** Apply every bucket's lifecycle rules once. Returns how many changes were made. */
function sweepLifecycle(now = null) {
  now = now || epoch();
  let changes = 0;
  for (const bucket of [...getStore().buckets.values()]) {
    const rules = lifecycleRules(bucket);
    if (!rules.length) continue;
    for (const key of [...bucket.keys()]) {
      const rec = bucket.objects.get(key);
      if (!rec) continue;
      changes += sweepKey(bucket, key, rec, rules, now);
    }
    for (const [uploadId, up] of [...bucket.uploads]) {
      for (const rule of rules) {
        if (rule.enabled && rule.abort_days !== null && up.key.startsWith(rule.prefix) && now - up.initiated >= rule.abort_days * DAY) {
          abortUpload(bucket, uploadId);
          changes += 1;
          break;
        }
      }
    }
  }
  if (changes) log("lifecycle:", changes, "changes");
  return changes;
}

function sweepKey(bucket, key, rec, rules, now) {
  let changes = 0;
  const versions = rec.versions;
  const current = versions[0];
  for (const rule of rules) {
    if (!current.dm && ruleMatches(rule, key, current)) {
      let due = (rule.exp_days !== null && now - current.time >= rule.exp_days * DAY) || (rule.exp_date !== null && now >= rule.exp_date);
      if (due && !locked(current, now)) {
        deleteObject(bucket, key, null, false);
        return 1;
      }
      for (const tr of rule.transitions) {
        due = (tr.days !== null && now - current.time >= tr.days * DAY) || (tr.date !== null && now >= tr.date);
        if (due && tr.class && g(current, "class", "STANDARD") !== tr.class) {
          current.class = tr.class;
          bucket.saveRecord(key);
          changes += 1;
        }
      }
    }
  }
  const noncurrent = versions.slice(1);
  for (const rule of rules) {
    if (!rule.enabled || !key.startsWith(rule.prefix)) continue;
    if (rule.nc_days !== null) {
      let kept = 0;
      for (const version of [...noncurrent]) {
        if (version.dm) continue;
        if (rule.nc_keep !== null && kept < rule.nc_keep) {
          kept += 1;
          continue;
        }
        // A version becomes noncurrent when the next newer one is written.
        const since = versions.at(versions.indexOf(version) - 1).time;
        if (now - since >= rule.nc_days * DAY && !locked(version, now)) {
          removeVersion(bucket, key, version.id);
          changes += 1;
        }
      }
    }
    for (const tr of rule.nc_transitions) {
      for (const version of versions.slice(1)) {
        const since = versions.at(versions.indexOf(version) - 1).time;
        if (!version.dm && tr.days !== null && now - since >= tr.days * DAY && tr.class && g(version, "class", "STANDARD") !== tr.class) {
          version.class = tr.class;
          bucket.saveRecord(key);
          changes += 1;
        }
      }
    }
  }
  const after = bucket.objects.get(key);
  if (after && after.versions.length === 1 && after.versions[0].dm) {
    if (rules.some((r) => r.enabled && r.exp_marker && key.startsWith(r.prefix))) {
      removeVersion(bucket, key, after.versions[0].id);
      changes += 1;
    }
  }
  return changes;
}

function lifecycleLoop() {
  const tick = () => {
    try {
      sweepLifecycle();
    } catch (err) {
      log("lifecycle error:", String(err && err.message ? err.message : err));
    }
    setTimeout(tick, LIFECYCLE_INTERVAL * 1000).unref();
  };
  setTimeout(tick, Math.min(60, LIFECYCLE_INTERVAL) * 1000).unref();
}

module.exports = { parseLifecycle, sweepLifecycle, lifecycleLoop };
