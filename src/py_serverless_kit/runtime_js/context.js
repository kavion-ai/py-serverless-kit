"use strict";
/** Provider-neutral invocation context (port of runtime/context.py). */

const { getLogger } = require("./log");
const { env, randomUUID } = require("./util");

class Context {
  /**
   * @param {{requestId?: string, function?: string, provider?: string, service?: string, stage?: string,
   *          region?: string, memoryMb?: number|null, deadline?: number|null, raw?: any,
   *          remaining?: () => number}} [init]
   */
  constructor(init = {}) {
    this.requestId = init.requestId || init.request_id || randomUUID();
    this.function = init.function || "";
    this.provider = init.provider || "local";
    this.service = init.service !== undefined ? init.service : env().PSKIT_SERVICE || "";
    this.stage = init.stage !== undefined ? init.stage : env().PSKIT_STAGE || "";
    this.region = init.region !== undefined ? init.region : env().PSKIT_REGION || "";
    this.memoryMb = init.memoryMb !== undefined ? init.memoryMb : init.memory_mb !== undefined ? init.memory_mb : null;
    /** Unix epoch seconds when the platform kills this invocation, if known. */
    this.deadline = init.deadline !== undefined ? init.deadline : null;
    this.raw = init.raw === undefined ? null : init.raw;
    this._remaining = typeof init.remaining === "function" ? init.remaining : null;
    this._logger = null;
  }

  get env() {
    return env();
  }

  get logger() {
    if (this._logger === null) {
      this._logger = getLogger("pskit.function", {
        function: this.function,
        request_id: this.requestId,
        provider: this.provider,
      });
    }
    return this._logger;
  }

  /** Milliseconds until the platform kills this invocation, or null when unknown. */
  remainingTimeMs() {
    if (this._remaining) return Math.trunc(this._remaining());
    if (this.deadline !== null && this.deadline !== undefined) {
      return Math.max(0, Math.trunc((this.deadline - Date.now() / 1000) * 1000));
    }
    return null;
  }
}

module.exports = { Context };
