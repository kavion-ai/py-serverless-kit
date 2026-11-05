// What a change to pskit.yml needs, kept the same as project_needs() in vault/permissions.py. The server decides;
// this only stops the screens offering what it would refuse.
import type { JsonObject } from "./types";
import { deepEqual } from "./util";

export type Action = "c" | "r" | "u" | "d";

const SECTIONS = ["functions", "workflows", "resources"];
const WORDS: Record<Action, string> = { c: "create", r: "read", u: "update", d: "delete" };

function isMap(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** The [feature, action] pairs saving `next` over `saved` takes: a new function is create, a removed one delete. */
export function projectNeeds(saved: JsonObject, next: JsonObject): [string, Action][] {
  const needs = new Map<string, [string, Action]>();
  const add = (feature: string, action: Action) => needs.set(feature + action, [feature, action]);
  for (const key of new Set([...Object.keys(saved), ...Object.keys(next)])) {
    const before = saved[key];
    const after = next[key];
    if (deepEqual(before, after)) continue;
    if (!SECTIONS.includes(key)) {
      add("project", "u");
    } else if ((before === undefined || isMap(before)) && (after === undefined || isMap(after))) {
      const from = (before ?? {}) as Record<string, unknown>;
      const to = (after ?? {}) as Record<string, unknown>;
      for (const name of new Set([...Object.keys(from), ...Object.keys(to)])) {
        if (!(name in from)) add(key, "c");
        else if (!(name in to)) add(key, "d");
        else if (!deepEqual(from[name] as never, to[name] as never)) add(key, "u");
      }
    } else {
      add(key, "u");
    }
  }
  return [...needs.values()];
}

export function describeNeed([feature, action]: [string, Action]): string {
  return `${WORDS[action]} permission on ${feature}`;
}

/** The feature whose rules apply to an edit at this path of pskit.yml. */
export function featureOfPath(head: string | number | undefined): string {
  return SECTIONS.includes(String(head)) ? String(head) : "project";
}
