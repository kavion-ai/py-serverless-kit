// Shared order logic: plain TypeScript, no cloud SDK.

export interface Order {
  id: string;
  item: string;
  quantity: number;
  unitPrice: number;
  total?: number;
  charged?: boolean;
}

export class ValidationError extends Error {}

/** Check an incoming order and compute its total. */
export function validate(input: unknown): Order {
  const raw = (input ?? {}) as Record<string, unknown>;
  const item = typeof raw.item === "string" ? raw.item.trim() : "";
  const quantity = Number(raw.quantity ?? 1);
  const unitPrice = Number(raw.unitPrice ?? 0);
  if (!item) throw new ValidationError("item is required");
  if (!Number.isInteger(quantity) || quantity < 1) throw new ValidationError("quantity must be a positive integer");
  if (!(unitPrice >= 0)) throw new ValidationError("unitPrice must be >= 0");
  const id = typeof raw.id === "string" && raw.id ? raw.id : `ord-${item.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return { id, item, quantity, unitPrice, total: Math.round(quantity * unitPrice * 100) / 100 };
}
