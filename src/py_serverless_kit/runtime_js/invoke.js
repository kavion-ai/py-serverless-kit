"use strict";
/**
 * Portable function-to-function invocation (port of runtime/invoke.py).
 *
 * `await invoke("billing", {order: 1})` calls another function of the same service:
 *
 * * `PSKIT_ENDPOINT_<NAME>` set   → HTTP POST to that URL (any provider)
 * * local / onprem                 → in-process call through the dispatcher
 * * aws                            → Lambda Invoke API (SigV4 with the function's credentials, no SDK)
 * * gcp                            → authenticated HTTPS call (ID token from the metadata server)
 */

const { env, nodeModule } = require("./util");

function crypto() {
  return nodeModule("crypto", true);
}
const { envelope } = require("./adapters/base");
const { loadManifest } = require("./manifest");

class InvokeError extends Error {
  constructor(message) {
    super(message);
    this.name = "InvokeError";
  }
}

function endpointKey(name) {
  return "PSKIT_ENDPOINT_" + String(name).replace(/[^A-Za-z0-9]/g, "_").toUpperCase();
}

function physicalName(fn) {
  const manifest = loadManifest();
  const spec = manifest.functions[fn];
  if (spec && spec.resourceName) return spec.resourceName;
  const service = manifest.service || env().PSKIT_SERVICE || "";
  const stage = manifest.stage || env().PSKIT_STAGE || "";
  return [service, stage, fn].filter(Boolean).join("-");
}

async function readBody(resp) {
  const raw = Buffer.from(await resp.arrayBuffer());
  if (!raw.length) return null;
  const text = raw.toString("utf8");
  try {
    return JSON.parse(text);
  } catch (err) {
    return text;
  }
}

async function httpPost(url, payload, timeout, headers = {}) {
  if (!/^https?:\/\//i.test(url)) throw new InvokeError(`invoke endpoint must be an http(s) URL, got '${url}'`);
  let resp;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: Object.assign({ "content-type": "application/json" }, headers),
      body: JSON.stringify(envelope("invoke", payload === undefined ? null : payload)),
      signal: AbortSignal.timeout(Math.round(timeout * 1000)),
    });
  } catch (err) {
    throw new InvokeError(`HTTP invoke of ${url} failed: ${err && err.message ? err.message : err}`);
  }
  return readBody(resp);
}

// ---------------------------------------------------------------- AWS SigV4

function hmac(key, text) {
  return crypto().createHmac("sha256", key).update(text, "utf8").digest();
}

function sha256(text) {
  return crypto().createHash("sha256").update(text).digest("hex");
}

/** Signed headers for an AWS JSON/REST request (credentials from the Lambda environment). */
function signAws({ method, host, path, region, service, body, headers }) {
  const accessKey = env().AWS_ACCESS_KEY_ID;
  const secretKey = env().AWS_SECRET_ACCESS_KEY;
  if (!accessKey || !secretKey) throw new InvokeError("AWS credentials are not available in the environment");
  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
  const day = amzDate.slice(0, 8);
  const all = Object.assign({ host, "x-amz-date": amzDate }, headers);
  if (env().AWS_SESSION_TOKEN) all["x-amz-security-token"] = env().AWS_SESSION_TOKEN;
  const names = Object.keys(all).map((k) => k.toLowerCase()).sort();
  const lower = {};
  for (const [k, v] of Object.entries(all)) lower[k.toLowerCase()] = String(v).trim();
  const canonical = [
    method,
    path.split("/").map((seg) => encodeURIComponent(seg)).join("/"),
    "",
    names.map((n) => `${n}:${lower[n]}`).join("\n") + "\n",
    names.join(";"),
    sha256(body),
  ].join("\n");
  const scope = `${day}/${region}/${service}/aws4_request`;
  const toSign = ["AWS4-HMAC-SHA256", amzDate, scope, sha256(canonical)].join("\n");
  const key = hmac(hmac(hmac(hmac(`AWS4${secretKey}`, day), region), service), "aws4_request");
  const signature = crypto().createHmac("sha256", key).update(toSign, "utf8").digest("hex");
  const out = Object.assign({}, all);
  delete out.host;
  out.authorization = `AWS4-HMAC-SHA256 Credential=${accessKey}/${scope}, SignedHeaders=${names.join(";")}, Signature=${signature}`;
  return out;
}

async function invokeAws(fn, payload, asynchronous, timeout) {
  const region = env().AWS_REGION || env().AWS_DEFAULT_REGION || env().PSKIT_REGION;
  if (!region) throw new InvokeError("AWS_REGION is not set");
  const host = `lambda.${region}.amazonaws.com`;
  const path = `/2015-03-31/functions/${physicalName(fn)}/invocations`;
  const body = JSON.stringify(envelope("invoke", payload === undefined ? null : payload));
  const headers = signAws({
    method: "POST",
    host,
    path,
    region,
    service: "lambda",
    body,
    headers: { "content-type": "application/json", "x-amz-invocation-type": asynchronous ? "Event" : "RequestResponse" },
  });
  const resp = await fetch(`https://${host}${path}`, {
    method: "POST",
    headers,
    body,
    signal: AbortSignal.timeout(Math.round(timeout * 1000)),
  });
  if (asynchronous) {
    if (!resp.ok) throw new InvokeError(`${fn} could not be queued: HTTP ${resp.status} ${await resp.text()}`);
    return null;
  }
  if (!resp.ok) throw new InvokeError(`${fn} could not be invoked: HTTP ${resp.status} ${await resp.text()}`);
  if (resp.headers.get("x-amz-function-error")) {
    throw new InvokeError(`${fn} failed: ${Buffer.from(await resp.arrayBuffer()).toString("utf8")}`);
  }
  return readBody(resp);
}

async function gcpIdToken(audience) {
  const url =
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity" +
    `?audience=${encodeURIComponent(audience)}`;
  const resp = await fetch(url, { headers: { "Metadata-Flavor": "Google" }, signal: AbortSignal.timeout(5000) });
  return (await resp.text()).trim();
}

/**
 * Invoke another function of this service and return its result.
 * @param {string} fn
 * @param {any} [payload]
 * @param {{async?: boolean, asynchronous?: boolean, timeout?: number}} [opts] timeout in seconds (default 30)
 */
async function invoke(fn, payload = null, opts = {}) {
  const asynchronous = !!(opts.async || opts.asynchronous);
  const timeout = opts.timeout === undefined ? 30 : Number(opts.timeout);
  const override = env()[endpointKey(fn)];
  if (override) return httpPost(override, payload, timeout);

  const provider = env().PSKIT_PROVIDER || "local";
  if (provider === "local" || provider === "onprem") {
    // In-process; `async` still finishes before invoke() resolves, as in a local run.
    const { execute } = require("./dispatch");
    const { Context } = require("./context");
    const { Event, EventType } = require("./event");
    const event = new Event({ type: EventType.INVOKE, provider, function: fn, data: payload });
    return execute(event, new Context({ function: fn, provider }), fn);
  }
  if (provider === "aws") return invokeAws(fn, payload, asynchronous, timeout);
  if (provider === "gcp") {
    const project = env().PSKIT_GCP_PROJECT || env().GOOGLE_CLOUD_PROJECT || "";
    const region = env().PSKIT_REGION || "";
    const url = `https://${region}-${project}.cloudfunctions.net/${physicalName(fn)}`;
    const token = await gcpIdToken(url);
    return httpPost(url, payload, timeout, { authorization: `Bearer ${token}` });
  }
  throw new InvokeError(
    `invoke() on provider '${provider}' needs the target URL in $${endpointKey(fn)}. ` +
      "Give the target function an http event and set that URL in the caller's environment.",
  );
}

module.exports = { invoke, InvokeError, physicalName, signAws };
