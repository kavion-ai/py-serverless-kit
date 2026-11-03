"use strict";
/**
 * Secrets from handlers with one call on every provider (port of runtime/secrets.py).
 *
 *   const { getSecret } = require("pskit");
 *   const password = await getSecret("db-password");
 *
 * The store comes from PSKIT_<STORE>_DRIVER / _URL / _TOKEN / _MOUNT / _REGION / _ACCESS_KEY / _SECRET_KEY
 * (default store "secrets"): vault (HashiCorp Vault / OpenBao KV v2), aws (Secrets Manager or LocalStack), infisical
 * (_URL, _CLIENT_ID / _CLIENT_SECRET or _TOKEN, _PROJECT_ID, _ENVIRONMENT, _PATH) or env (PSKIT_SECRET_<NAME>, then
 * <NAME>). No dependencies.
 */

const TTL_MS = 60000;
const cache = new Map();

class SecretError extends Error {}
class SecretNotFound extends SecretError {}

function varName(name) {
  return String(name).toUpperCase().replace(/[^A-Z0-9]/g, "_");
}

function config(store) {
  const name = store || process.env.PSKIT_SECRETS_STORE || "secrets";
  const prefix = `PSKIT_${varName(name)}_`;
  const cfg = { store: name };
  for (const [k, v] of Object.entries(process.env)) if (k.startsWith(prefix)) cfg[k.slice(prefix.length).toLowerCase()] = v;
  cfg.driver = (cfg.driver || (cfg.url && cfg.token ? "vault" : "env")).toLowerCase();
  return cfg;
}

function fields(text) {
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const out = {};
      for (const [k, v] of Object.entries(parsed)) out[k] = typeof v === "string" ? v : JSON.stringify(v);
      return out;
    }
  } catch (_e) {
    // a plain string
  }
  return { value: String(text) };
}

async function http(method, url, headers, body) {
  let resp;
  try {
    resp = await fetch(url, { method, headers, body, signal: AbortSignal.timeout(10000) });
  } catch (err) {
    throw new SecretError(`secret store ${new URL(url).host} is unreachable: ${err.message}`);
  }
  return { status: resp.status, text: await resp.text() };
}

async function vaultRead(cfg, name) {
  const mount = cfg.mount || "secret";
  const r = await http("GET", `${cfg.url.replace(/\/$/, "")}/v1/${mount}/data/${encodeURIComponent(name)}`, { "X-Vault-Token": cfg.token || "" });
  if (r.status === 404) throw new SecretNotFound(`secret ${name} not found in ${cfg.store} (${mount}/)`);
  if (r.status !== 200) throw new SecretError(`vault: reading ${name} failed (${r.status}): ${r.text.slice(0, 200)}`);
  const data = ((JSON.parse(r.text).data || {}).data) || {};
  return fields(JSON.stringify(data));
}

async function vaultWrite(cfg, name, values) {
  const mount = cfg.mount || "secret";
  const r = await http("POST", `${cfg.url.replace(/\/$/, "")}/v1/${mount}/data/${encodeURIComponent(name)}`,
    { "X-Vault-Token": cfg.token || "", "Content-Type": "application/json" }, JSON.stringify({ data: values }));
  if (r.status !== 200 && r.status !== 204) throw new SecretError(`vault: writing ${name} failed (${r.status}): ${r.text.slice(0, 200)}`);
}

function awsSign(cfg, region, url, body, target) {
  const crypto = require("crypto");
  const accessKey = cfg.access_key || process.env.AWS_ACCESS_KEY_ID;
  const secretKey = cfg.secret_key || process.env.AWS_SECRET_ACCESS_KEY;
  if (!accessKey || !secretKey) throw new SecretError("aws secrets: no credentials (PSKIT_<STORE>_ACCESS_KEY / AWS_ACCESS_KEY_ID)");
  const sha = (t) => crypto.createHash("sha256").update(t).digest("hex");
  const hmac = (k, t) => crypto.createHmac("sha256", k).update(t, "utf8").digest();
  const amzDate = new Date().toISOString().replace(/[:-]|\.\d{3}/g, "");
  const day = amzDate.slice(0, 8);
  const all = { host: url.host, "x-amz-date": amzDate, "content-type": "application/x-amz-json-1.1", "x-amz-target": `secretsmanager.${target}` };
  if (!cfg.access_key && process.env.AWS_SESSION_TOKEN) all["x-amz-security-token"] = process.env.AWS_SESSION_TOKEN;
  const names = Object.keys(all).sort();
  const canonical = ["POST", url.pathname || "/", "", names.map((n) => `${n}:${all[n]}`).join("\n") + "\n", names.join(";"), sha(body)].join("\n");
  const scope = `${day}/${region}/secretsmanager/aws4_request`;
  const key = hmac(hmac(hmac(hmac(`AWS4${secretKey}`, day), region), "secretsmanager"), "aws4_request");
  const signature = crypto.createHmac("sha256", key).update(["AWS4-HMAC-SHA256", amzDate, scope, sha(canonical)].join("\n"), "utf8").digest("hex");
  const headers = Object.assign({}, all);
  delete headers.host;
  headers.authorization = `AWS4-HMAC-SHA256 Credential=${accessKey}/${scope}, SignedHeaders=${names.join(";")}, Signature=${signature}`;
  return headers;
}

async function awsCall(cfg, target, payload) {
  const region = cfg.region || process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-east-1";
  const url = new URL((cfg.url || `https://secretsmanager.${region}.amazonaws.com`).replace(/\/$/, "") + "/");
  const body = JSON.stringify(payload);
  const r = await http("POST", url.toString(), awsSign(cfg, region, url, body, target), body);
  let data = {};
  try {
    data = r.text.trim() ? JSON.parse(r.text) : {};
  } catch (_e) {
    data = { message: r.text.slice(0, 200) };
  }
  return { status: r.status, data };
}

async function awsRead(cfg, name) {
  const { status, data } = await awsCall(cfg, "GetSecretValue", { SecretId: name });
  if (status === 400 && String(data.__type || "").includes("ResourceNotFound")) throw new SecretNotFound(`secret ${name} not found in ${cfg.store} (Secrets Manager)`);
  if (status !== 200) throw new SecretError(`secretsmanager: reading ${name} failed (${status}): ${data.message || data.Message || JSON.stringify(data)}`);
  return fields(data.SecretString || "");
}

async function awsWrite(cfg, name, values) {
  const text = Object.keys(values).length === 1 && "value" in values ? values.value : JSON.stringify(values);
  let { status, data } = await awsCall(cfg, "PutSecretValue", { SecretId: name, SecretString: text, ClientRequestToken: require("crypto").randomUUID() });
  if (status === 400 && String(data.__type || "").includes("ResourceNotFound")) ({ status, data } = await awsCall(cfg, "CreateSecret", { Name: name, SecretString: text, ClientRequestToken: require("crypto").randomUUID() }));
  if (status !== 200) throw new SecretError(`secretsmanager: writing ${name} failed (${status}): ${data.message || data.Message || JSON.stringify(data)}`);
}

async function envRead(_cfg, name) {
  for (const v of [`PSKIT_SECRET_${varName(name)}`, varName(name)]) if (v in process.env) return fields(process.env[v]);
  throw new SecretNotFound(`secret ${name} not found: set PSKIT_SECRET_${varName(name)} (or ${varName(name)}), or configure a store (PSKIT_SECRETS_URL / _TOKEN)`);
}

const tokens = new Map();

async function infisicalToken(cfg) {
  if (cfg.token) return cfg.token;
  if (!cfg.client_id || !cfg.client_secret) {
    throw new SecretError(`infisical: set PSKIT_${varName(cfg.store)}_CLIENT_ID and _CLIENT_SECRET (a machine identity with Universal Auth) or _TOKEN`);
  }
  const url = String(cfg.url || "").replace(/\/+$/, "");
  const hit = tokens.get(url + cfg.client_id);
  if (hit && hit.until > Date.now()) return hit.token;
  const r = await http("POST", `${url}/api/v1/auth/universal-auth/login`, { "Content-Type": "application/json" },
    JSON.stringify({ clientId: cfg.client_id, clientSecret: cfg.client_secret }));
  if (r.status !== 200) throw new SecretError(`infisical: login failed (${r.status}): ${r.text.slice(0, 200)}`);
  const data = JSON.parse(r.text);
  tokens.set(url + cfg.client_id, { token: data.accessToken, until: Date.now() + (Math.max(60, data.expiresIn || 600) - 30) * 1000 });
  return data.accessToken;
}

function infisicalScope(cfg) {
  if (!cfg.project_id) throw new SecretError(`infisical: set PSKIT_${varName(cfg.store)}_PROJECT_ID (Project settings -> Project ID)`);
  return { workspaceId: cfg.project_id, environment: cfg.environment || "dev", secretPath: cfg.path || "/" };
}

async function infisicalRead(cfg, name) {
  const url = String(cfg.url || "").replace(/\/+$/, "");
  const query = new URLSearchParams(infisicalScope(cfg)).toString();
  const r = await http("GET", `${url}/api/v3/secrets/raw/${encodeURIComponent(name)}?${query}`, { Authorization: `Bearer ${await infisicalToken(cfg)}` });
  if (r.status === 404) throw new SecretNotFound(`secret ${name} not found in ${cfg.store} (infisical)`);
  if (r.status !== 200) throw new SecretError(`infisical: reading ${name} failed (${r.status}): ${r.text.slice(0, 200)}`);
  return fields(String((JSON.parse(r.text).secret || {}).secretValue || ""));
}

async function infisicalWrite(cfg, name, values) {
  const url = String(cfg.url || "").replace(/\/+$/, "");
  const keys = Object.keys(values);
  const text = keys.length === 1 && keys[0] === "value" ? values.value : JSON.stringify(values, keys.sort());
  const body = JSON.stringify({ ...infisicalScope(cfg), secretValue: text, type: "shared" });
  const headers = { Authorization: `Bearer ${await infisicalToken(cfg)}`, "Content-Type": "application/json" };
  let r = await http("PATCH", `${url}/api/v3/secrets/raw/${encodeURIComponent(name)}`, headers, body);
  if (r.status === 400 || r.status === 404) r = await http("POST", `${url}/api/v3/secrets/raw/${encodeURIComponent(name)}`, headers, body);
  if (r.status !== 200) throw new SecretError(`infisical: writing ${name} failed (${r.status}): ${r.text.slice(0, 200)}`);
}

const READ = { vault: vaultRead, aws: awsRead, env: envRead, infisical: infisicalRead };
const WRITE = { vault: vaultWrite, aws: awsWrite, infisical: infisicalWrite };

/** Every field of a secret ({value} for a plain one). Cached for 60 s. */
async function getSecrets(name, opts = {}) {
  const cfg = config(opts.store);
  const reader = READ[cfg.driver];
  if (!reader) throw new SecretError(`unknown secrets driver ${cfg.driver} (vault, aws, infisical or env)`);
  const key = `${cfg.store}\u0000${name}`;
  const hit = cache.get(key);
  if (hit && !opts.refresh && Date.now() - hit.at < TTL_MS) return Object.assign({}, hit.values);
  const values = await reader(cfg, name);
  cache.set(key, { at: Date.now(), values });
  return Object.assign({}, values);
}

/** One value: `field` of the secret, or its only / `value` field. `opts.default` instead of SecretNotFound. */
async function getSecret(name, field, opts = {}) {
  if (field && typeof field === "object") [opts, field] = [field, undefined];
  let values;
  try {
    values = await getSecrets(name, opts);
  } catch (err) {
    if (err instanceof SecretNotFound && opts.default !== undefined) return opts.default;
    throw err;
  }
  if (field === undefined || field === null) {
    if ("value" in values) return values.value;
    const keys = Object.keys(values);
    return keys.length === 1 ? values[keys[0]] : JSON.stringify(values);
  }
  if (field in values) return values[field];
  if (opts.default !== undefined) return opts.default;
  throw new SecretNotFound(`secret ${name} has no field ${field} (fields: ${Object.keys(values).sort().join(", ")})`);
}

/** Create or update a secret: a string (stored as `value`) or an object of fields. */
async function putSecret(name, value, opts = {}) {
  const cfg = config(opts.store);
  const writer = WRITE[cfg.driver];
  if (!writer) throw new SecretError(`the ${cfg.driver} secrets driver is read-only; write with your provider's tools`);
  const values = {};
  if (value && typeof value === "object") for (const [k, v] of Object.entries(value)) values[k] = String(v);
  else values.value = String(value);
  await writer(cfg, name, values);
  cache.delete(`${cfg.store}\u0000${name}`);
}

module.exports = { getSecret, getSecrets, putSecret, SecretError, SecretNotFound };
