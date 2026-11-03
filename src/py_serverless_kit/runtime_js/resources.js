"use strict";
/**
 * Read the `resources:` bindings of the current function (port of runtime/resources.py).
 *
 *   PSKIT_RESOURCES=uploads,jobs
 *   PSKIT_RESOURCE_UPLOADS_TYPE / _NAME / _EXTERNAL / _<CONNECTION KEY> / _ARN / _URL / _ID
 */

const { env: currentEnv } = require("./util");

const FIXED = new Set(["TYPE", "NAME", "EXTERNAL"]);

function envKey(text) {
  return String(text).replace(/[^A-Za-z0-9]/g, "_").toUpperCase();
}

class Resource {
  constructor({ name, type, nativeName, external = false, connection = {} }) {
    this.name = name;
    this.type = type;
    this.nativeName = nativeName;
    this.external = external;
    this.connection = Object.assign({}, connection);
  }

  /** Connection value by case-insensitive key, e.g. `res.get("endpoint")`. */
  get(key, fallback = null) {
    const k = String(key).toLowerCase();
    return Object.prototype.hasOwnProperty.call(this.connection, k) ? this.connection[k] : fallback;
  }

  /** Like get() but throws when missing (Python `res["key"]`). */
  require(key) {
    const value = this.get(key);
    if (value === null) {
      const known = Object.keys(this.connection).sort().join(", ") || "<none>";
      throw new Error(`resource '${this.name}' has no '${key}'; known: ${known}`);
    }
    return value;
  }

  get arn() {
    return this.get("arn");
  }

  get url() {
    return this.get("url");
  }

  get id() {
    return this.get("id");
  }
}

function names(env) {
  return String(env.PSKIT_RESOURCES || "")
    .split(",")
    .map((n) => n.trim())
    .filter(Boolean);
}

function build(name, env, all) {
  const prefix = `PSKIT_RESOURCE_${envKey(name)}_`;
  // Variables of a longer resource key (`a` vs `a_b`) share this prefix: skip them.
  const longer = all
    .filter((other) => envKey(other) !== envKey(name) && `PSKIT_RESOURCE_${envKey(other)}_`.startsWith(prefix))
    .map((other) => `PSKIT_RESOURCE_${envKey(other)}_`);
  const connection = {};
  for (const [variable, value] of Object.entries(env)) {
    if (!variable.startsWith(prefix) || longer.some((o) => variable.startsWith(o))) continue;
    const suffix = variable.slice(prefix.length);
    if (suffix && !FIXED.has(suffix)) connection[suffix.toLowerCase()] = value;
  }
  return new Resource({
    name,
    type: env[prefix + "TYPE"] || "",
    nativeName: env[prefix + "NAME"] || name,
    external: String(env[prefix + "EXTERNAL"] || "false").toLowerCase() === "true",
    connection,
  });
}

/** Every resource bound to the current function. */
function resources(env = currentEnv()) {
  const all = names(env);
  const out = {};
  for (const name of all) out[name] = build(name, env, all);
  return out;
}

/** The binding of resource `name` (the key under `resources:` in pskit.yml). */
function resource(name, env = currentEnv()) {
  const all = names(env);
  let match = all.find((n) => n === name);
  if (match === undefined) match = all.find((n) => envKey(n) === envKey(name));
  if (match === undefined) {
    const known = all.join(", ") || "<none>";
    throw new Error(
      `resource '${name}' is not bound to this function; bound: ${known}. ` +
        "Check `resources:` and its `functions:` list in pskit.yml.",
    );
  }
  return build(match, env, all);
}

module.exports = { Resource, resources, resource };
