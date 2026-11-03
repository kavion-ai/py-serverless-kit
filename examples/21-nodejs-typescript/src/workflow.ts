// Workflow tasks: each returns the state's output, which becomes the next state's input.
import type { Event } from "pskit";
import { validate } from "./orders";

export { ValidationError } from "./orders";

/** Throws ValidationError for a bad order; the workflow catches it and fails with OrderRejected. */
export async function validateOrder(event: Event) {
  return validate(event.data);
}

export async function chargeOrder(event: Event) {
  const order = event.data as Record<string, unknown>;
  return { ...order, charged: true, chargedAt: new Date(0).toISOString() };
}
