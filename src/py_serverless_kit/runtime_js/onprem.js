"use strict";
/**
 * Publish through the on-premises host from a Node.js handler (port of the Python
 * `submit_queue` / `submit_topic` / `put_object` / `delete_object` in runtime/onprem_host.py).
 *
 *   const { resource, submitQueue } = require("pskit");
 *   const id = await submitQueue(resource("jobs").nativeName, { orderId: 1 }, { kind: "new" });
 *
 * The host honours the resource's driver (built-in folder, Redis, Kafka, SQS, ...).
 * It sets PSKIT_HOST_URL (its loopback address) and, when it has one, PSKIT_ADMIN_TOKEN.
 */

const { env: currentEnv } = require("./util");

function hostUrl(env) {
  const base = (env || currentEnv()).PSKIT_HOST_URL;
  if (!base) throw new Error("PSKIT_HOST_URL is not set: these helpers work in functions run by the on-prem host");
  return base.replace(/\/+$/, "");
}

async function call(method, path, body, raw, env) {
  const e = env || currentEnv();
  const headers = {};
  if (e.PSKIT_ADMIN_TOKEN) headers["x-pskit-token"] = e.PSKIT_ADMIN_TOKEN;
  let data;
  if (raw !== undefined) {
    data = raw;
  } else if (body !== undefined) {
    headers["content-type"] = "application/json";
    data = JSON.stringify(body);
  }
  const resp = await fetch(hostUrl(e) + path, { method, headers, body: data });
  const text = await resp.text();
  const parsed = text ? JSON.parse(text) : null;
  if (!resp.ok) throw new Error(`on-prem host answered ${resp.status}: ${(parsed && (parsed.error || parsed.cause)) || text}`);
  return parsed;
}

const seg = (s) => encodeURIComponent(String(s));
const keyPath = (key) => String(key).split("/").filter(Boolean).map(seg).join("/");

/** Send a message to queue `name`; resolves to the message id. */
async function submitQueue(name, message, attributes = {}, env) {
  const out = await call("POST", `/__pskit/queues/${seg(name)}`, { message, attributes }, undefined, env);
  return ((out && out.queued) || [])[0] || "";
}

/** Publish a message to topic `name`; resolves to the message id. */
async function submitTopic(name, message, attributes = {}, env) {
  const out = await call("POST", `/__pskit/topics/${seg(name)}`, { message, attributes }, undefined, env);
  return ((out && out.published) || [])[0] || "";
}

/** Write an object (string or Buffer) to bucket `bucket`. */
async function putObject(bucket, key, data, env) {
  await call("PUT", `/__pskit/storage/${seg(bucket)}/${keyPath(key)}`, undefined, typeof data === "string" ? data : Buffer.from(data), env);
}

/** Delete an object; resolves to true when it existed. */
async function deleteObject(bucket, key, env) {
  const out = await call("DELETE", `/__pskit/storage/${seg(bucket)}/${keyPath(key)}`, undefined, undefined, env);
  return Boolean(out && out.deleted);
}

module.exports = { submitQueue, submitTopic, putObject, deleteObject };
