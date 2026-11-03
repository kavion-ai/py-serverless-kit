"use strict";
/**
 * Structured JSON logging (port of runtime/log.py).
 *
 * One JSON object per line with the same fields as the Python runtime:
 * `ts`, `level`, `logger`, `message`, bound fields (`function`, `request_id`,
 * `provider`), call-site fields and `exception`. `PSKIT_LOG_FORMAT=text` gives
 * `2026-01-02 03:04:05,123 INFO    pskit.function: message`.
 * `PSKIT_LOG_LEVEL` / `LOG_LEVEL` set the level (default INFO).
 *
 * Lines go to stdout, like Python. The worker (worker.js) redirects stdout to
 * stderr because it uses stdout for its protocol.
 */

const { env, isoformat } = require("./util");
const { asciiOnly } = require("./response");

const LEVELS = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 };
// Keys of a Python LogRecord: an extra field with one of these names gets a trailing "_".
const RESERVED = new Set([
  "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text",
  "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName",
  "processName", "process", "taskName", "message", "asctime",
]);

function threshold() {
  const raw = String(env().PSKIT_LOG_LEVEL || env().LOG_LEVEL || "INFO").toUpperCase();
  if (raw in LEVELS) return LEVELS[raw];
  const n = Number(raw);
  return Number.isFinite(n) ? n : LEVELS.INFO;
}

function textTime(date) {
  const iso = date.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)},${iso.slice(20, 23)}`;
}

function safeJson(payload) {
  const seen = new WeakSet();
  return JSON.stringify(payload, function replacer(key, value) {
    const original = this[key];
    if (original instanceof Date) return isoformat(original);
    if (Buffer.isBuffer(original)) return original.toString("utf8");
    if (typeof value === "bigint") return String(value);
    if (value instanceof Error) return `${value.name}: ${value.message}`;
    if (value instanceof Map) return Object.fromEntries(value);
    if (value instanceof Set) return Array.from(value);
    if (value && typeof value === "object") {
      if (seen.has(value)) return "[Circular]";
      seen.add(value);
    }
    if (typeof value === "function" || typeof value === "symbol") return String(value);
    return value;
  });
}

class Logger {
  /**
   * @param {string} name logger name (always starts with "pskit")
   * @param {Record<string, any>} fields fields added to every line
   */
  constructor(name = "pskit.function", fields = {}) {
    this.name = name.startsWith("pskit") ? name : `pskit.${name}`;
    this.fields = Object.assign({}, fields);
  }

  /** A logger with extra bound fields. */
  child(fields) {
    return new Logger(this.name, Object.assign({}, this.fields, fields || {}));
  }

  isEnabledFor(level) {
    return (LEVELS[level] || 0) >= threshold();
  }

  log(level, message, fields, error) {
    if (!this.isEnabledFor(level)) return;
    const now = new Date();
    let line;
    if (String(env().PSKIT_LOG_FORMAT || "json").toLowerCase() === "text") {
      line = `${textTime(now)} ${level.padEnd(7)} ${this.name}: ${message}`;
      if (error) line += `\n${error && error.stack ? error.stack : String(error)}`;
    } else {
      const payload = { ts: isoformat(now), level, logger: this.name, message: String(message) };
      const merged = Object.assign({}, this.fields, fields || {});
      let exc = error;
      if (merged.exc_info !== undefined) {
        if (merged.exc_info instanceof Error) exc = merged.exc_info;
        delete merged.exc_info;
      }
      for (const [k, v] of Object.entries(merged)) payload[RESERVED.has(k) ? `${k}_` : k] = v;
      if (exc) payload.exception = exc && exc.stack ? exc.stack : String(exc);
      try {
        line = asciiOnly(safeJson(payload));
      } catch (err) {
        line = JSON.stringify({ ts: payload.ts, level, logger: this.name, message: String(message) });
      }
    }
    try {
      if (typeof process !== "undefined" && process.stdout && typeof process.stdout.write === "function") {
        process.stdout.write(line + "\n");
      } else {
        console.log(line); // Cloudflare Workers and other runtimes without process.stdout
      }
    } catch (err) {
      // A log call must never crash a handler.
    }
  }

  debug(message, fields) {
    this.log("DEBUG", message, fields);
  }

  info(message, fields) {
    this.log("INFO", message, fields);
  }

  warning(message, fields) {
    this.log("WARNING", message, fields);
  }

  warn(message, fields) {
    this.log("WARNING", message, fields);
  }

  error(message, fields, error) {
    if (fields instanceof Error) return this.log("ERROR", message, undefined, fields);
    this.log("ERROR", message, fields, error);
  }

  /** `logger.exception(msg, err)`: ERROR with the stack trace. */
  exception(message, error, fields) {
    this.log("ERROR", message, fields, error);
  }

  critical(message, fields) {
    this.log("CRITICAL", message, fields);
  }
}

function getLogger(name = "pskit.function", fields = {}) {
  return new Logger(name, fields);
}

module.exports = { Logger, getLogger, LEVELS };
