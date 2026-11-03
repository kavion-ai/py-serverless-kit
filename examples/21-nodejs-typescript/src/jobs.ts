// Queue and schedule handlers.
import { BatchResult } from "pskit";
import type { Context, Event } from "pskit";
import { validate } from "./orders";

/** Queue consumer: a bad message fails alone and is retried (then dead-lettered); the rest succeed. */
export async function processOrders(event: Event, ctx: Context) {
  const result = new BatchResult();
  for (const record of event.records) {
    try {
      const order = validate(record.json());
      ctx.logger.info("processed order", { id: order.id, total: order.total });
    } catch (err) {
      ctx.logger.warning("rejected message", { id: record.id, error: String(err) });
      result.fail(record);
    }
  }
  return result;
}

/** Runs on a schedule; `event.data` is the `input` from pskit.yml. */
export async function nightlyReport(event: Event, ctx: Context) {
  ctx.logger.info("nightly report", { input: event.data });
  return { ok: true, report: (event.data as { report?: string } | null)?.report ?? "daily" };
}
