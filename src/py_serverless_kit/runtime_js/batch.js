"use strict";
/** Partial batch failure reporting for queue / topic / storage events (port of runtime/batch.py). */

const BATCH = Symbol.for("pskit.BatchResult");

/** Thrown on providers without partial-batch support so the whole batch retries. */
class BatchFailure extends Error {
  constructor(failedIds) {
    super(`${failedIds.length} record(s) failed: ${failedIds.slice(0, 10).join(", ")}`);
    this.name = "BatchFailure";
    this.failedIds = failedIds;
  }
}

/**
 * Return this from a batch handler to retry only the records that failed.
 * On AWS SQS it becomes `batchItemFailures`; on most other providers any
 * failure makes the whole invocation fail (and therefore retry).
 */
class BatchResult {
  constructor(failed = []) {
    this.failed = Array.from(failed);
    Object.defineProperty(this, BATCH, { value: true });
  }

  /** @param {{id?: string|null}|string} record */
  fail(record) {
    const id = record !== null && typeof record === "object" ? record.id : record;
    if (id !== null && id !== undefined) this.failed.push(String(id));
  }

  static of(failed) {
    const result = new BatchResult();
    for (const item of failed || []) result.fail(item);
    return result;
  }

  get ok() {
    return this.failed.length === 0;
  }

  raiseIfFailed() {
    if (this.failed.length) throw new BatchFailure(this.failed);
  }
}

function isBatchResult(value) {
  return !!value && typeof value === "object" && value[BATCH] === true;
}

module.exports = { BatchResult, BatchFailure, isBatchResult };
