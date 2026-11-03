"use strict";
/**
 * Exceptions a handler can throw to produce a well-formed HTTP error response
 * (port of runtime/errors.py). For non-HTTP events they are re-thrown so the
 * platform's retry / dead-letter semantics apply unchanged.
 *
 * Instances carry a `Symbol.for("pskit.HttpError")` brand so a copy of this
 * package (node_modules/pskit vs pskit_runtime) is still recognised.
 */

const HTTP_ERROR = Symbol.for("pskit.HttpError");

class PskitError extends Error {
  constructor(message) {
    super(message);
    this.name = new.target.name;
  }
}

/** The configured `module.function` handler could not be imported. */
class HandlerNotFound extends PskitError {}

/** No function matches (Python raises LookupError). */
class LookupError extends PskitError {}

class HttpError extends Error {
  /**
   * @param {string} [message]
   * @param {{status?: number, details?: any, headers?: Record<string, string>}} [opts]
   */
  constructor(message, opts = {}) {
    const defaults = new.target.defaults || HttpError.defaults;
    const text = message || defaults.message;
    super(text);
    this.name = new.target.name;
    this.message = text;
    this.status = opts.status !== undefined && opts.status !== null ? opts.status : defaults.status;
    this.details = opts.details === undefined ? null : opts.details;
    this.headers = Object.assign({}, opts.headers || {});
    Object.defineProperty(this, HTTP_ERROR, { value: true });
  }

  toBody() {
    const body = { error: this.message, status: this.status };
    if (this.details !== null && this.details !== undefined) body.details = this.details;
    return body;
  }
}
HttpError.defaults = { status: 500, message: "Internal Server Error" };

function httpError(name, status, message) {
  const cls = { [name]: class extends HttpError {} }[name];
  cls.defaults = { status, message };
  return cls;
}

const BadRequest = httpError("BadRequest", 400, "Bad Request");
const Unauthorized = httpError("Unauthorized", 401, "Unauthorized");
const Forbidden = httpError("Forbidden", 403, "Forbidden");
const NotFound = httpError("NotFound", 404, "Not Found");
const MethodNotAllowed = httpError("MethodNotAllowed", 405, "Method Not Allowed");
const Conflict = httpError("Conflict", 409, "Conflict");
const UnprocessableEntity = httpError("UnprocessableEntity", 422, "Unprocessable Entity");
const TooManyRequests = httpError("TooManyRequests", 429, "Too Many Requests");

function isHttpError(value) {
  return !!value && typeof value === "object" && value[HTTP_ERROR] === true;
}

/** Error name as Python reports it: `err.error`, else the class name (`Flaky`, `TypeError`, ...). */
function errorName(err) {
  if (err && typeof err === "object") {
    if (typeof err.error === "string" && err.error) return err.error;
    const ctor = err.constructor && err.constructor.name;
    if (ctor && ctor !== "Object") return ctor;
    if (typeof err.name === "string" && err.name) return err.name;
  }
  return "Error";
}

/** `str(exc)` of Python: the message. */
function errorText(err) {
  if (err && typeof err === "object" && "message" in err) return String(err.message);
  return String(err);
}

module.exports = {
  PskitError,
  HandlerNotFound,
  LookupError,
  HttpError,
  BadRequest,
  Unauthorized,
  Forbidden,
  NotFound,
  MethodNotAllowed,
  Conflict,
  UnprocessableEntity,
  TooManyRequests,
  isHttpError,
  errorName,
  errorText,
};
