"use strict";
// The Secrets Manager API operations (OPERATIONS), which of them only read (READS), and run(), which calls one.

const crypto = require("crypto");
const { ACCOUNT, LOWER, UPPER, DIGITS, PUNCTUATION, NAME_RE } = require("./config");
const { ApiError, invalid, badRequest } = require("./errors");
const { store } = require("./store");
const { log, has, now, today } = require("./util");
const {
  requestToken, secretValue, parseTags, mergeTags, sameValue, drop, moveStage, addVersion, pickVersion, valueOut,
  describe, page, matches, sortedSecrets, randomFrom,
} = require("./values");

const OPERATIONS = {
  CreateSecret(p, region) {
    const name = p.Name;
    if (typeof name !== "string" || !NAME_RE.test(name)) throw invalid("Name must be 1-512 characters of letters, digits and /_+=.@-");
    const value = secretValue(p);
    const token = requestToken(p);
    const existing = store.secrets[name];
    if (existing) {
      if (existing.DeletedDate) {
        throw badRequest("You can't create this secret because a secret with this name is already scheduled for deletion.");
      }
      const version = existing.Versions[token];
      if (value && version && sameValue(version, value)) return { ARN: existing.ARN, Name: name, VersionId: token };
      throw new ApiError("ResourceExistsException", `The operation failed because the secret ${name} already exists.`);
    }
    const alnum = LOWER + UPPER + DIGITS;
    let suffix = "";
    for (let i = 0; i < 6; i += 1) suffix += randomFrom(alnum);
    const t = now();
    const secret = {
      Name: name,
      ARN: `arn:aws:secretsmanager:${region}:${ACCOUNT}:secret:${name}-${suffix}`,
      CreatedDate: t,
      LastChangedDate: t,
      Tags: parseTags(p.Tags),
      Versions: {},
    };
    if (has(p, "Description")) secret.Description = String(p.Description);
    if (p.KmsKeyId) {
      store.keyring.keyId(p.KmsKeyId, true);
      secret.KmsKeyId = String(p.KmsKeyId);
    }
    const out = { ARN: secret.ARN, Name: name };
    if (value) {
      addVersion(secret, token, value, null);
      out.VersionId = token;
    }
    store.secrets[name] = secret;
    store.save();
    return out;
  },

  GetSecretValue(p) {
    const secret = store.live(p.SecretId);
    const [vid, version] = pickVersion(secret, p);
    if (secret.LastAccessedDate !== today()) {
      secret.LastAccessedDate = today();
      store.save();
    }
    return valueOut(secret, vid, version);
  },

  BatchGetSecretValue(p, region) {
    const ids = p.SecretIdList;
    const filters = p.Filters;
    if (ids && ids.length && filters && filters.length) throw invalid("Use either SecretIdList or Filters, not both.");
    const values = [];
    const errors = [];
    const one = (sid) => {
      try {
        values.push(OPERATIONS.GetSecretValue({ SecretId: sid }, region));
      } catch (err) {
        if (!(err instanceof ApiError)) throw err;
        errors.push({ SecretId: sid, ErrorCode: err.code, Message: err.message });
      }
    };
    if (ids && ids.length) {
      if (!Array.isArray(ids) || ids.length > 20) throw invalid("SecretIdList holds 1-20 secret ids.");
      ids.forEach(one);
      return { SecretValues: values, Errors: errors };
    }
    const matched = sortedSecrets().filter((s) => !s.DeletedDate && matches(s, filters));
    const [chunk, next] = page(p, matched, 20);
    for (const secret of chunk) one(secret.Name);
    const out = { SecretValues: values, Errors: errors };
    if (next) out.NextToken = next;
    return out;
  },

  PutSecretValue(p) {
    const secret = store.live(p.SecretId);
    const value = secretValue(p, true);
    const token = requestToken(p);
    const stages = addVersion(secret, token, value, p.VersionStages);
    store.save();
    return { ARN: secret.ARN, Name: secret.Name, VersionId: token, VersionStages: stages };
  },

  UpdateSecret(p) {
    const secret = store.live(p.SecretId);
    const value = secretValue(p);
    if (p.KmsKeyId) store.keyring.keyId(p.KmsKeyId, true);
    const out = { ARN: secret.ARN, Name: secret.Name };
    if (has(p, "Description")) secret.Description = String(p.Description);
    if (p.KmsKeyId) secret.KmsKeyId = String(p.KmsKeyId);
    if (value) {
      const token = requestToken(p);
      addVersion(secret, token, value, null);
      out.VersionId = token;
    }
    secret.LastChangedDate = now();
    store.save();
    return out;
  },

  DescribeSecret(p) {
    return describe(store.find(p.SecretId));
  },

  ListSecrets(p) {
    const items = sortedSecrets().filter((s) => (p.IncludePlannedDeletion || !s.DeletedDate) && matches(s, p.Filters));
    if (p.SortOrder === "desc") items.reverse();
    else if (has(p, "SortOrder") && p.SortOrder !== "asc") throw invalid("SortOrder must be asc or desc.");
    const [chunk, next] = page(p, items);
    const out = { SecretList: chunk.map((s) => describe(s, true)) };
    if (next) out.NextToken = next;
    return out;
  },

  DeleteSecret(p) {
    const secret = store.find(p.SecretId);
    const force = Boolean(p.ForceDeleteWithoutRecovery);
    if (force && has(p, "RecoveryWindowInDays")) {
      throw invalid("You can't use ForceDeleteWithoutRecovery in conjunction with RecoveryWindowInDays.");
    }
    const out = { ARN: secret.ARN, Name: secret.Name };
    if (force) {
      delete store.secrets[secret.Name];
      out.DeletionDate = now();
    } else {
      if (secret.DeletedDate) {
        throw badRequest("You can't perform this operation on the secret because it was already scheduled for deletion.");
      }
      const days = Number(has(p, "RecoveryWindowInDays") ? p.RecoveryWindowInDays : 30);
      if (!Number.isInteger(days)) throw invalid("RecoveryWindowInDays must be a number.");
      if (days < 7 || days > 30) throw invalid("RecoveryWindowInDays must be between 7 and 30 days.");
      secret.DeletedDate = now();
      secret.DeletionDate = Math.round(Date.now() + days * 86400 * 1000) / 1000;
      out.DeletionDate = secret.DeletionDate;
    }
    store.save();
    return out;
  },

  RestoreSecret(p) {
    const secret = store.find(p.SecretId);
    delete secret.DeletedDate;
    delete secret.DeletionDate;
    store.save();
    return { ARN: secret.ARN, Name: secret.Name };
  },

  ListSecretVersionIds(p) {
    const secret = store.find(p.SecretId);
    let versions = Object.entries(secret.Versions).sort((a, b) => b[1].CreatedDate - a[1].CreatedDate);
    if (!p.IncludeDeprecated) versions = versions.filter(([, v]) => v.Stages.length);
    const rows = versions.map(([vid, v]) => ({ VersionId: vid, VersionStages: [...v.Stages], CreatedDate: v.CreatedDate }));
    const [chunk, next] = page(p, rows);
    const out = { ARN: secret.ARN, Name: secret.Name, Versions: chunk };
    if (next) out.NextToken = next;
    return out;
  },

  UpdateSecretVersionStage(p) {
    const secret = store.live(p.SecretId);
    const stage = p.VersionStage;
    if (typeof stage !== "string" || !stage) throw invalid("VersionStage is required.");
    const removeFrom = p.RemoveFromVersionId;
    const moveTo = p.MoveToVersionId;
    const versions = secret.Versions;
    const holder = Object.keys(versions).find((vid) => versions[vid].Stages.includes(stage));
    if (holder && moveTo && holder !== moveTo && removeFrom !== holder) {
      throw invalid(`The staging label ${stage} is currently attached to version ${holder}, so you must explicitly reference that version in RemoveFromVersionId.`);
    }
    for (const vid of [removeFrom, moveTo]) if (vid && !versions[vid]) throw invalid(`Version ${vid} does not exist.`);
    if (moveTo) moveStage(secret, stage, moveTo);
    else if (removeFrom) {
      if (stage === "AWSCURRENT") throw invalid("You can't remove AWSCURRENT; move it to another version instead.");
      drop(versions[removeFrom].Stages, stage);
    }
    secret.LastChangedDate = now();
    store.save();
    return { ARN: secret.ARN, Name: secret.Name };
  },

  TagResource(p) {
    const secret = store.find(p.SecretId);
    secret.Tags = mergeTags(secret.Tags || [], parseTags(p.Tags));
    store.save();
    return {};
  },

  UntagResource(p) {
    const secret = store.find(p.SecretId);
    const keys = p.TagKeys || [];
    if (!Array.isArray(keys)) throw invalid("TagKeys must be a list.");
    secret.Tags = (secret.Tags || []).filter((t) => !keys.includes(t.Key));
    store.save();
    return {};
  },

  GetRandomPassword(p) {
    const length = Number(p.PasswordLength || 32);
    if (!Number.isInteger(length)) throw invalid("PasswordLength must be a number.");
    if (length < 1 || length > 4096) throw invalid("PasswordLength must be between 1 and 4096.");
    const exclude = String(p.ExcludeCharacters || "");
    let groups = [];
    if (!p.ExcludeLowercase) groups.push(LOWER);
    if (!p.ExcludeUppercase) groups.push(UPPER);
    if (!p.ExcludeNumbers) groups.push(DIGITS);
    if (!p.ExcludePunctuation) groups.push(PUNCTUATION);
    if (p.IncludeSpace) groups.push(" ");
    groups = groups.map((g) => [...g].filter((c) => !exclude.includes(c)).join("")).filter(Boolean);
    if (!groups.length) throw invalid("The password has no characters left to use.");
    const every = has(p, "RequireEachIncludedType") ? Boolean(p.RequireEachIncludedType) : true;
    if (every && length < groups.length) throw invalid("PasswordLength is too short to include every character type.");
    const pool = groups.join("");
    const chars = every ? groups.map(randomFrom) : [];
    while (chars.length < length) chars.push(randomFrom(pool));
    for (let i = chars.length - 1; i > 0; i -= 1) {
      const j = crypto.randomInt(i + 1);
      [chars[i], chars[j]] = [chars[j], chars[i]];
    }
    return { RandomPassword: chars.join("") };
  },

  PutResourcePolicy(p) {
    const secret = store.live(p.SecretId);
    try {
      JSON.parse(String(p.ResourcePolicy));
    } catch {
      throw new ApiError("MalformedPolicyDocumentException", "ResourcePolicy must be a JSON policy document.");
    }
    secret.ResourcePolicy = String(p.ResourcePolicy);
    store.save();
    return { ARN: secret.ARN, Name: secret.Name };
  },

  GetResourcePolicy(p) {
    const secret = store.find(p.SecretId);
    const out = { ARN: secret.ARN, Name: secret.Name };
    if (secret.ResourcePolicy) out.ResourcePolicy = secret.ResourcePolicy;
    return out;
  },

  DeleteResourcePolicy(p) {
    const secret = store.find(p.SecretId);
    delete secret.ResourcePolicy;
    store.save();
    return { ARN: secret.ARN, Name: secret.Name };
  },

  ValidateResourcePolicy(p) {
    try {
      JSON.parse(String(p.ResourcePolicy));
    } catch {
      throw new ApiError("MalformedPolicyDocumentException", "ResourcePolicy must be a JSON policy document.");
    }
    return { PolicyValidationPassed: true, ValidationErrors: [] };
  },
};

for (const name of ["RotateSecret", "CancelRotateSecret", "ReplicateSecretToRegions", "RemoveRegionsFromReplication", "StopReplicationToReplica"]) {
  OPERATIONS[name] = () => {
    throw badRequest(`${name} is not supported by this Secrets Manager compatible server (no rotation functions or replica regions).`);
  };
}

// Operations that change nothing: they are not logged.
const READS = new Set(["GetSecretValue", "BatchGetSecretValue", "DescribeSecret", "ListSecrets", "ListSecretVersionIds",
  "GetRandomPassword", "GetResourcePolicy", "ValidateResourcePolicy"]);

function run(operation, params, region, who) {
  if (!Object.prototype.hasOwnProperty.call(OPERATIONS, operation)) {
    throw new ApiError("UnknownOperationException", `Operation ${operation} is not known.`);
  }
  if (!params || typeof params !== "object" || Array.isArray(params)) {
    throw new ApiError("SerializationException", "The request body must be a JSON object.");
  }
  // Node runs one request at a time here (every operation is synchronous), so no lock is needed.
  store.purge();
  const out = OPERATIONS[operation](params, region);
  if (!READS.has(operation)) log(operation, params.SecretId || params.Name || "", "by", who);
  return out;
}

module.exports = { OPERATIONS, READS, run };
