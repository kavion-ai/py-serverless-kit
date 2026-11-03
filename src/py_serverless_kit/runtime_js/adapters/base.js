"use strict";
/** Helpers shared by all adapters (port of runtime/adapters/base.py). */

const { EventType } = require("../event");
const { env } = require("../util");

const ENVELOPE_KEY = "__pskit";

/**
 * Wrap a payload so any adapter can recognise its event type. The CLI uses this
 * for schedule inputs, workflow task payloads and function-to-function invoke
 * calls, because those arrive on most clouds as an opaque JSON object.
 */
function envelope(kind, data = null, meta = {}) {
  return Object.assign({ [ENVELOPE_KEY]: kind, data }, meta || {});
}

/** Decode Buffer / string holding JSON; return the input unchanged otherwise. */
function maybeJson(value) {
  let v = value;
  if (Buffer.isBuffer(v) || v instanceof Uint8Array) {
    const buf = Buffer.from(v);
    const text = buf.toString("utf8");
    if (!Buffer.from(text, "utf8").equals(buf)) return value;
    v = text;
  }
  if (typeof v === "string") {
    const text = v.trim();
    if (text.startsWith("{") || text.startsWith("[") || text === "null" || text === "true" || text === "false") {
      try {
        return JSON.parse(text);
      } catch (err) {
        return v;
      }
    }
  }
  return v;
}

/** `[kind, data, meta]` when `obj` is a `__pskit` envelope, else null. */
function unwrapEnvelope(obj) {
  let o = obj;
  if (typeof o === "string" || Buffer.isBuffer(o)) o = maybeJson(o);
  if (o && typeof o === "object" && !Array.isArray(o) && Object.prototype.hasOwnProperty.call(o, ENVELOPE_KEY)) {
    let kind = o[ENVELOPE_KEY];
    if (!EventType.ALL.includes(kind)) kind = EventType.INVOKE;
    const meta = {};
    for (const [k, v] of Object.entries(o)) if (k !== ENVELOPE_KEY && k !== "data") meta[k] = v;
    return [kind, o.data === undefined ? null : o.data, meta];
  }
  return null;
}

/** Decode a base64 field to text (or the raw Buffer when it isn't UTF-8); used by Pub/Sub style payloads. */
function b64Text(value) {
  if (!value) return null;
  let raw;
  try {
    raw = Buffer.from(String(value), "base64");
  } catch (err) {
    return value;
  }
  const text = raw.toString("utf8");
  return Buffer.from(text, "utf8").equals(raw) ? text : raw;
}

function functionName(fallback = "") {
  return env().PSKIT_FUNCTION || fallback;
}

/** Map provider-specific object event names to `created` / `deleted`. */
function actionFrom(name) {
  const lowered = String(name || "").toLowerCase();
  if (["delete", "remove", "archive"].some((w) => lowered.includes(w))) return "deleted";
  return "created";
}

function first(mapping, ...keys) {
  for (const key of keys) {
    if (mapping && mapping[key] !== undefined && mapping[key] !== null) return mapping[key];
  }
  return null;
}

module.exports = { ENVELOPE_KEY, envelope, maybeJson, unwrapEnvelope, b64Text, functionName, actionFrom, first };
