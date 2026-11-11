"use strict";
// Helpers of the operations: request parameters (tokens, values, tags), versions and staging labels, the response
// shapes, paging and ListSecrets filters.

const crypto = require("crypto");
const { MAX_VALUE, MAX_VERSIONS } = require("./config");
const { ApiError, invalid } = require("./errors");
const { store } = require("./store");
const { has, now, byCodePoint } = require("./util");

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

function randomFrom(chars) {
  return chars[crypto.randomInt(chars.length)];
}

module.exports = {
  requestToken, secretValue, parseTags, mergeTags, stagesOf, sameValue, drop, moveStage, prune, addVersion,
  pickVersion, valueOut, describe, page, matches, sortedSecrets, randomFrom,
};
