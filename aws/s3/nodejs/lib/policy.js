"use strict";
// The bucket policy engine: principals, actions, resources and conditions (../../ARCHITECTURE.md, "Bucket policies").
// policyDecision() answers "deny", "allow" or ""; access.allowed() turns that into the final decision.

const net = require("net");

const { asList, isDict, own, pyStr } = require("./py");
const { ACCOUNT } = require("./config");
const { epoch, parseTime } = require("./util");

/** Condition keys that tie an Allow to a network, account or organization: such an Allow is not public. */
const RESTRICTING_KEYS = new Set(["aws:sourceip", "aws:sourcevpc", "aws:sourcevpce", "aws:sourceaccount", "aws:sourcearn",
  "aws:principalaccount", "aws:principalorgid"]);
/** Request headers available to conditions as s3:<header>. */
const CONDITION_HEADERS = ["x-amz-acl", "x-amz-server-side-encryption", "x-amz-storage-class", "x-amz-content-sha256"];
const SIGNATURE_VERSIONS = { sigv4: "AWS4-HMAC-SHA256", sigv2: "AWS" };
const TAG_KEY = "s3:existingobjecttag/";

/** `*` matches any run of characters, `?` any one character (newlines included). */
function like(pattern, value, ignoreCase) {
  const regex = pattern.split("*").map((p) => p.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&").replace(/\\\?/g, ".")).join(".*");
  return new RegExp(`^${regex}$`, ignoreCase ? "isu" : "su").test(value);
}

// ----------------------------------------------------------------------------- statements

/** Whether a Principal / NotPrincipal value names the requester (an access key id, or null when anonymous). */
function namesRequester(principal, who) {
  if (principal === "*") return true;
  if (!isDict(principal)) return false;
  const ids = who === null ? ["*"]
    : ["*", ACCOUNT, `arn:aws:iam::${ACCOUNT}:root`, who, `arn:aws:iam::${ACCOUNT}:user/${who}`];
  return asList(principal.AWS).some((entry) => typeof entry === "string" && ids.includes(entry));
}

function principalMatches(st, who) {
  if (own(st, "Principal")) return namesRequester(st.Principal, who);
  if (own(st, "NotPrincipal")) return !namesRequester(st.NotPrincipal, who);
  return false;
}

/** Action / NotAction or Resource / NotResource: whether the statement covers `value`. */
function listMatches(st, field, notField, value, ignoreCase) {
  const hit = (list) => asList(list).some((p) => typeof p === "string" && like(p, value, ignoreCase));
  if (own(st, field)) return hit(st[field]);
  if (own(st, notField)) return !hit(st[notField]);
  return false;
}

/** An Allow that names anyone (or everyone but someone, with NotPrincipal). */
function forEveryone(st) {
  if (own(st, "NotPrincipal")) return true;
  const principal = st.Principal;
  return principal === "*" || (isDict(principal) && asList(principal.AWS).includes("*"));
}

/** A condition on the source network, account or organization. */
function restricted(st) {
  if (!isDict(st.Condition)) return false;
  const restricting = (block) => isDict(block) && Object.keys(block).some((k) => RESTRICTING_KEYS.has(k.toLowerCase()));
  return Object.values(st.Condition).some(restricting);
}

const statementPublic = (st) => isDict(st) && st.Effect === "Allow" && forEveryone(st) && !restricted(st);

// ----------------------------------------------------------------------------- condition keys

/** An address as the policy sees it: IPv4-mapped IPv6 (::ffff:127.0.0.1) becomes plain IPv4. */
function normalizeIp(ip) {
  const textIp = String(ip || "").trim();
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/i.exec(textIp);
  return mapped ? mapped[1] : textIp;
}

const isLoopback = (ip) => ip === "::1" || /^127\.\d+\.\d+\.\d+$/.test(ip);

/**
 * The condition key values of a request: lower-case key -> value. aws:SourceIp is the TCP peer; X-Forwarded-For and
 * X-Forwarded-Proto count only when the peer is this host (a local reverse proxy).
 */
function contextOf(req) {
  const peer = normalizeIp(req.ip);
  const local = isLoopback(peer);
  const forwarded = (req.headers["x-forwarded-for"] || "").split(",")[0].trim();
  const secure = local && (req.headers["x-forwarded-proto"] || "").trim().toLowerCase() === "https";
  const now = epoch();
  const values = new Map([
    ["aws:sourceip", local && forwarded ? normalizeIp(forwarded) : peer],
    ["aws:securetransport", secure ? "true" : "false"],
    ["aws:currenttime", new Date(Math.floor(now) * 1000).toISOString().replace(/\.\d+Z$/, "Z")],
    ["aws:epochtime", String(Math.floor(now))],
    ["aws:principaltype", req.who === null ? "Anonymous" : "Account"],
  ]);
  const put = (key, value) => {
    if (value !== undefined) values.set(key, value);
  };
  put("aws:referer", req.headers.referer);
  put("aws:useragent", req.headers["user-agent"]);
  if (req.who !== null) {
    values.set("aws:username", req.who);
    values.set("aws:userid", req.who);
    values.set("aws:principalaccount", ACCOUNT);
    if (req.auth.via) values.set("s3:authtype", req.auth.via);
    put("s3:signatureversion", SIGNATURE_VERSIONS[req.auth.mode]);
  }
  for (const name of ["prefix", "delimiter", "max-keys"]) put(`s3:${name}`, req.q[name]);
  put("s3:versionid", req.q.versionId);
  for (const name of CONDITION_HEADERS) put(`s3:${name}`, req.headers[name]);
  return values;
}

/** The request's values of a condition key (case-insensitive; tag names keep their case), or null when it has none. */
function lookup(values, key, tags) {
  const low = key.toLowerCase();
  if (low.startsWith(TAG_KEY)) {
    const name = key.slice(TAG_KEY.length);
    return own(tags, name) ? [String(tags[name])] : null;
  }
  return values.has(low) ? [values.get(low)] : null;
}

// ----------------------------------------------------------------------------- condition operators

const number = (s) => (/^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/.test(s) ? Number(s) : null);
/** A date as epoch seconds: a number of seconds or an ISO 8601 / RFC 2822 date. */
const date = (s) => (number(s) !== null ? number(s) : parseTime(s));

function compare(parse, test) {
  return (value, wanted) => {
    const a = parse(value);
    const b = parse(wanted);
    return a !== null && b !== null && test(a, b);
  };
}

/** Whether address `ip` is in `cidr` (an address alone is a /32 or /128). */
function inNetwork(ip, cidr) {
  const [base, bits] = cidr.trim().split("/");
  const family = net.isIP(base);
  const ipFamily = net.isIP(ip);
  if (!family || family !== ipFamily || (bits !== undefined && !/^\d+$/.test(bits))) return false;
  const prefix = bits === undefined ? (family === 4 ? 32 : 128) : Number(bits);
  if (prefix > (family === 4 ? 32 : 128)) return false;
  const list = new net.BlockList();
  list.addSubnet(base, prefix, family === 4 ? "ipv4" : "ipv6");
  return list.check(ip, family === 4 ? "ipv4" : "ipv6");
}

const equal = (a, b) => a === b;
const sameText = (a, b) => a.toLowerCase() === b.toLowerCase();
const stringLike = (value, wanted) => like(wanted, value, false);
const numeric = (test) => compare(number, test);
const dated = (test) => compare(date, test);

/** operator -> [test(request value, policy value), negated]. A negated operator holds when no policy value matches. */
const OPERATORS = {
  StringEquals: [equal, false],
  StringNotEquals: [equal, true],
  StringEqualsIgnoreCase: [sameText, false],
  StringNotEqualsIgnoreCase: [sameText, true],
  StringLike: [stringLike, false],
  StringNotLike: [stringLike, true],
  NumericEquals: [numeric(equal), false],
  NumericNotEquals: [numeric(equal), true],
  NumericLessThan: [numeric((a, b) => a < b), false],
  NumericLessThanEquals: [numeric((a, b) => a <= b), false],
  NumericGreaterThan: [numeric((a, b) => a > b), false],
  NumericGreaterThanEquals: [numeric((a, b) => a >= b), false],
  DateEquals: [dated(equal), false],
  DateNotEquals: [dated(equal), true],
  DateLessThan: [dated((a, b) => a < b), false],
  DateLessThanEquals: [dated((a, b) => a <= b), false],
  DateGreaterThan: [dated((a, b) => a > b), false],
  DateGreaterThanEquals: [dated((a, b) => a >= b), false],
  Bool: [sameText, false],
  IpAddress: [inNetwork, false],
  NotIpAddress: [inNetwork, true],
};

/** A policy value as text: JSON true / false and numbers are written without quotes in policies. */
const valueText = (value) => (typeof value === "boolean" ? String(value) : pyStr(value));

/** Request values against policy values: one holds when it matches any policy value (negated: none of them). */
function valuesHold(values, wanted, [test, negated], qualifier) {
  const holds = (value) => wanted.some((w) => test(value, w)) !== negated;
  return qualifier === "ForAllValues" ? values.every(holds) : values.some(holds);
}

/**
 * One operator block, e.g. "ForAnyValue:StringLikeIfExists": {key: values}. Every key must hold. A missing key fails a
 * positive operator and passes a negated one; IfExists passes it; an unknown operator fails.
 */
function operatorHolds(opText, block, values, tags) {
  let op = opText;
  let qualifier = "";
  for (const prefix of ["ForAnyValue:", "ForAllValues:"]) {
    if (op.startsWith(prefix)) {
      qualifier = prefix.slice(0, -1);
      op = op.slice(prefix.length);
    }
  }
  const ifExists = op.endsWith("IfExists");
  if (ifExists) op = op.slice(0, -"IfExists".length);
  if (!isDict(block)) return false;
  for (const [key, want] of Object.entries(block)) {
    const found = lookup(values, key, tags);
    const wanted = asList(want).map(valueText);
    let holds;
    if (op === "Null") holds = wanted.some((w) => (w.toLowerCase() === "true") === (found === null));
    else if (!own(OPERATORS, op)) return false;
    else if (found === null) holds = ifExists || OPERATORS[op][1];
    else holds = valuesHold(found, wanted, OPERATORS[op], qualifier);
    if (!holds) return false;
  }
  return true;
}

/** A statement's Condition: every operator must hold (none at all holds). */
function conditionsHold(condition, values, tags) {
  if (condition === undefined || condition === null) return true;
  if (!isDict(condition)) return false;
  return Object.entries(condition).every(([op, block]) => operatorHolds(op, block, values, tags));
}

// ----------------------------------------------------------------------------- decisions

/** The statements of a bucket's policy ([] when there is none or it is not a JSON object), parsed once per change. */
function statementsOf(bucket) {
  if (own(bucket.parsed, "policy")) return bucket.parsed.policy;
  let statements = [];
  if (bucket.meta.policy) {
    try {
      const policy = JSON.parse(bucket.meta.policy);
      if (isDict(policy)) statements = asList(policy.Statement);
    } catch {
      statements = [];
    }
  }
  bucket.parsed.policy = statements;
  return statements;
}

/**
 * The bucket policy's answer for `action` by the requester of `req`: "deny" when a Deny statement applies, else
 * "allow" when an Allow does, else "". `key` names the object and `version` its existing version (for its tags).
 */
function policyDecision(bucket, req, action, key = "", version = null) {
  const statements = statementsOf(bucket);
  const resource = `arn:aws:s3:::${bucket.name}${key ? `/${key}` : ""}`;
  const tags = version && isDict(version.tags) ? version.tags : {};
  let values = null;
  let decision = "";
  for (const st of statements) {
    if (!isDict(st) || !principalMatches(st, req.who)) continue;
    if (!listMatches(st, "Action", "NotAction", action, true)) continue;
    if (!listMatches(st, "Resource", "NotResource", resource, false)) continue;
    if (own(st, "Condition")) {
      values = values || contextOf(req);
      if (!conditionsHold(st.Condition, values, tags)) continue;
    }
    if (st.Effect === "Deny") return "deny";
    if (st.Effect === "Allow") decision = "allow";
  }
  return decision;
}

/** Whether a policy document (parsed) is public: an Allow for anyone without a restricting condition. */
const statementsPublic = (policy) => isDict(policy) && asList(policy.Statement).some(statementPublic);

/** policyStatus.IsPublic of a bucket. */
const policyIsPublic = (bucket) => statementsOf(bucket).some(statementPublic);

module.exports = { policyDecision, statementsPublic, policyIsPublic };
