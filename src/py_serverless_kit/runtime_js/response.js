"use strict";
/** Provider-neutral HTTP response model (port of runtime/response.py). */

const { isoformat } = require("./util");

const RESPONSE = Symbol.for("pskit.Response");
const TEXT_TYPES = new Set([
  "application/json",
  "application/xml",
  "application/javascript",
  "application/x-www-form-urlencoded",
  "image/svg+xml",
]);

/** JSON like Python `json.dumps(..., separators=(",", ":"), default=json_default)`. */
function dumps(value) {
  const text = JSON.stringify(value === undefined ? null : value, function replacer(key, v) {
    const original = this[key];
    if (original instanceof Date) return isoformat(original);
    if (Buffer.isBuffer(original)) return original.toString("utf8");
    if (original instanceof Uint8Array) return Buffer.from(original).toString("utf8");
    if (typeof v === "bigint") return Number(v);
    if (v instanceof Set) return Array.from(v).sort();
    if (v instanceof Map) return Object.fromEntries(v);
    if (v && typeof v === "object" && typeof v.toDict === "function" && !Array.isArray(v)) return v.toDict();
    return v;
  });
  return text === undefined ? "null" : asciiOnly(text);
}

/** Python json.dumps escapes every non-ASCII character (ensure_ascii=True). */
function asciiOnly(text) {
  return text.replace(/[\u0080-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
}

function isTextContentType(contentType) {
  const ct = String(contentType || "").split(";")[0].trim().toLowerCase();
  return ct.startsWith("text/") || TEXT_TYPES.has(ct) || ct.endsWith("+json");
}

class Response {
  /**
   * @param {number} [status]
   * @param {any} [body] string, Buffer, null, or any JSON value
   * @param {Record<string, string>} [headers]
   */
  constructor(status = 200, body = null, headers = {}) {
    this.status = status;
    this.body = body;
    this.headers = Object.assign({}, headers || {});
    this.cookies = [];
    Object.defineProperty(this, RESPONSE, { value: true });
  }

  static json(data, status = 200, headers = {}) {
    return new Response(status, dumps(data), Object.assign({ "content-type": "application/json" }, headers || {}));
  }

  static text(text, status = 200, headers = {}) {
    return new Response(status, String(text), Object.assign({ "content-type": "text/plain; charset=utf-8" }, headers || {}));
  }

  static html(html, status = 200, headers = {}) {
    return new Response(status, String(html), Object.assign({ "content-type": "text/html; charset=utf-8" }, headers || {}));
  }

  static binary(data, contentType = "application/octet-stream", status = 200, headers = {}) {
    return new Response(status, Buffer.from(data), Object.assign({ "content-type": contentType }, headers || {}));
  }

  static redirect(location, status = 302) {
    return new Response(status, "", { location });
  }

  static noContent() {
    return new Response(204, "");
  }

  /** Python `no_content`. */
  static no_content() {
    return Response.noContent();
  }

  setCookie(name, value, { maxAge = null, path = "/", httpOnly = true, secure = true, sameSite = "Lax" } = {}) {
    const parts = [`${name}=${value}`, `Path=${path}`, `SameSite=${sameSite}`];
    if (maxAge !== null && maxAge !== undefined) parts.push(`Max-Age=${maxAge}`);
    if (httpOnly) parts.push("HttpOnly");
    if (secure) parts.push("Secure");
    this.cookies.push(parts.join("; "));
    return this;
  }

  get contentType() {
    for (const [k, v] of Object.entries(this.headers)) if (k.toLowerCase() === "content-type") return v;
    return "";
  }

  /** `{status, headers, body: Buffer}` with lower-cased header names and a content-type when there is a body. */
  render() {
    const headers = {};
    for (const [k, v] of Object.entries(this.headers)) headers[k.toLowerCase()] = String(v);
    const body = this.body;
    let raw;
    if (body === null || body === undefined) {
      raw = Buffer.alloc(0);
    } else if (Buffer.isBuffer(body) || body instanceof Uint8Array) {
      raw = Buffer.from(body);
      if (raw.length && !("content-type" in headers)) headers["content-type"] = "application/octet-stream";
    } else if (typeof body === "string") {
      raw = Buffer.from(body, "utf8");
      if (raw.length && !("content-type" in headers)) headers["content-type"] = "text/plain; charset=utf-8";
    } else {
      raw = Buffer.from(dumps(body), "utf8");
      if (!("content-type" in headers)) headers["content-type"] = "application/json";
    }
    return { status: Number(this.status), headers, body: raw };
  }

  /** Like render() but a string body plus `isBase64`, which API-gateway style integrations expect. */
  renderForGateway() {
    const { status, headers, body } = this.render();
    if (!body.length) return { status, headers, body: "", isBase64: false };
    if (isTextContentType(headers["content-type"] || "")) {
      const text = body.toString("utf8");
      if (Buffer.from(text, "utf8").equals(body)) return { status, headers, body: text, isBase64: false };
    }
    return { status, headers, body: body.toString("base64"), isBase64: true };
  }
}

function isResponse(value) {
  return !!value && typeof value === "object" && value[RESPONSE] === true;
}

/**
 * Coerce what a handler returned into a Response:
 * Response unchanged; null/undefined → 204; string → text/plain; Buffer → octet-stream; anything else → JSON 200.
 */
function toResponse(result) {
  if (isResponse(result)) return result;
  if (result === null || result === undefined) return Response.noContent();
  if (Buffer.isBuffer(result) || result instanceof Uint8Array) return Response.binary(result);
  if (typeof result === "string") return Response.text(result);
  return Response.json(result);
}

module.exports = { Response, toResponse, isResponse, dumps, asciiOnly, isTextContentType };
