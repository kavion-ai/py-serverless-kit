// HTTP handlers. The same code runs on every cloud pskit deploys to.
import { BadRequest, NotFound, Response } from "pskit";
import type { Context, Event } from "pskit";
import { validate, ValidationError } from "./orders";

const KNOWN: Record<string, { id: string; item: string; status: string }> = {
  "ord-1": { id: "ord-1", item: "book", status: "shipped" },
};

export async function hello(event: Event, ctx: Context) {
  const name = event.http?.query.name ?? "world";
  ctx.logger.info("saying hello", { name });
  return { message: `Hello, ${name}!`, provider: event.provider, stage: ctx.stage };
}

export async function createOrder(event: Event, ctx: Context) {
  try {
    const order = validate(event.http?.json());
    ctx.logger.info("order accepted", { id: order.id, total: order.total });
    return Response.json(order, 201);
  } catch (err) {
    if (err instanceof ValidationError) throw new BadRequest(err.message);
    throw err;
  }
}

export async function getOrder(event: Event) {
  const id = event.http!.pathParams.id;
  const order = KNOWN[id];
  if (!order) throw new NotFound(`order ${id} does not exist`);
  return order;
}
