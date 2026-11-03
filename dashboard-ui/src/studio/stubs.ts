import { api } from "./api";

/** Handler stubs queued by "create on save"; written after pskit.yml is saved. */
const pending = new Map<string, { events: Set<string>; subproject: boolean }>();

/** `subproject`: also give the handler's folder its own requirements.txt / package.json. */
export function queueHandlerStub(handler: string, events: string[], subproject = false): void {
  const entry = pending.get(handler) || { events: new Set<string>(), subproject: false };
  events.forEach((e) => entry.events.add(e));
  if (!events.length) entry.events.add("invoke");
  entry.subproject = entry.subproject || subproject;
  pending.set(handler, entry);
}

export function forgetHandlerStub(handler: string): void {
  pending.delete(handler);
}

/** Write every queued stub. Returns how many files were changed. Never throws. */
export async function flushHandlerStubs(): Promise<number> {
  let created = 0;
  for (const [handler, entry] of Array.from(pending.entries())) {
    try {
      const res = await api.ensureHandler(handler, Array.from(entry.events), entry.subproject);
      if (res.created) created++;
      pending.delete(handler);
    } catch {
      // keep it queued; the next save retries
    }
  }
  return created;
}
