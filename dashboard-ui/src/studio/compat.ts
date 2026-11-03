/**
 * What in the draft can't run on a provider, and the edits that switch it off there.
 *
 * "Off on one provider" is written as a `providers.<cloud>` override, which pskit merges over the
 * top-level config only when deploying to that cloud:
 *   providers.<cloud>.functions.<fn>.enabled: false     skip the function
 *   providers.<cloud>.functions.<fn>.events: [...]      the function's triggers on that cloud
 *   providers.<cloud>.workflows.<wf>.enabled: false     skip the workflow
 * `enabled: false` at the top level switches an item off everywhere.
 */
import type { Json, JsonObject, ProviderMeta } from "./types";
import { asArray, asObject, getIn, normalizeEvent, setIn, str } from "./util";

export interface CompatProblem {
  key: string;
  kind: "trigger" | "workflow" | "workflow-task";
  fn?: string;
  wf?: string;
  types?: string[];
  message: string;
}

function override(draft: JsonObject, provider: string, section: "functions" | "workflows", name: string): JsonObject {
  return asObject(getIn(draft, ["providers", provider, section, name]));
}

/** Is the function / workflow deployed to `provider` (top-level and per-provider `enabled`)? */
export function isEnabled(draft: JsonObject, provider: string, section: "functions" | "workflows", name: string): boolean {
  const base = asObject(asObject(draft[section])[name]);
  const over = override(draft, provider, section, name);
  if (over.enabled !== undefined) return over.enabled !== false;
  return base.enabled !== false;
}

/** The triggers a function gets on `provider` (a per-provider `events` list replaces the top-level one). */
export function eventsOn(draft: JsonObject, provider: string, fn: string): Json[] {
  const over = override(draft, provider, "functions", fn);
  if (Array.isArray(over.events)) return over.events;
  return asArray(asObject(asObject(draft.functions)[fn]).events);
}

function taskFunctions(def: Json): string[] {
  const out: string[] = [];
  for (const st of Object.values(asObject(asObject(def).states))) {
    const s = asObject(st);
    if (typeof s.function === "string") out.push(s.function);
    asArray(s.branches).forEach((b) => out.push(...taskFunctions(b)));
    if (s.iterator) out.push(...taskFunctions(s.iterator));
  }
  return out;
}

export function compatProblems(draft: JsonObject, provider: ProviderMeta): CompatProblem[] {
  const problems: CompatProblem[] = [];
  const caps = new Set(provider.capabilities);
  for (const fn of Object.keys(asObject(draft.functions))) {
    if (!isEnabled(draft, provider.name, "functions", fn)) continue;
    const bad = Array.from(
      new Set(
        eventsOn(draft, provider.name, fn)
          .map((e) => normalizeEvent(e)?.type)
          .filter((t): t is NonNullable<typeof t> => !!t && !caps.has(t)),
      ),
    );
    if (bad.length) {
      problems.push({
        key: `fn:${fn}`,
        kind: "trigger",
        fn,
        types: bad,
        message: `${fn}: ${bad.join(", ")} trigger${bad.length > 1 ? "s are" : " is"} not available on ${provider.display_name}`,
      });
    }
  }
  for (const [wf, def] of Object.entries(asObject(draft.workflows))) {
    if (!isEnabled(draft, provider.name, "workflows", wf)) continue;
    if (str(asObject(def).engine) === "native" && !caps.has("workflow_native")) {
      problems.push({ key: `wf:${wf}`, kind: "workflow", wf, message: `workflow ${wf}: ${provider.display_name} has no native workflow engine` });
    }
    const off = Array.from(new Set(taskFunctions(def))).filter((f) => f in asObject(draft.functions) && !isEnabled(draft, provider.name, "functions", f));
    if (off.length) {
      problems.push({
        key: `wft:${wf}`,
        kind: "workflow-task",
        wf,
        message: `workflow ${wf} calls ${off.join(", ")}, which ${off.length > 1 ? "are" : "is"} disabled on ${provider.display_name}`,
      });
    }
  }
  return problems;
}

/** Drop the given trigger types from `fn`, on `provider` only. */
export function skipTriggersOn(draft: JsonObject, provider: string, fn: string, types: string[]): JsonObject {
  const kept = eventsOn(draft, provider, fn).filter((e) => !types.includes(normalizeEvent(e)?.type || ""));
  return setIn(draft, ["providers", provider, "functions", fn, "events"], kept) as JsonObject;
}

/** Remove the per-provider trigger list so the function uses its top-level triggers again. */
export function restoreTriggersOn(draft: JsonObject, provider: string, fn: string): JsonObject {
  return prune(setIn(draft, ["providers", provider, "functions", fn, "events"], undefined) as JsonObject, provider);
}

export function setEnabledOn(
  draft: JsonObject,
  provider: string | null,
  section: "functions" | "workflows",
  name: string,
  enabled: boolean,
): JsonObject {
  if (provider === null) {
    // Everywhere: top-level flag; drop per-provider flags that would contradict it.
    let raw = setIn(draft, [section, name, "enabled"], enabled ? undefined : false) as JsonObject;
    for (const p of Object.keys(asObject(raw.providers))) {
      if (getIn(raw, ["providers", p, section, name, "enabled"]) !== undefined) {
        raw = prune(setIn(raw, ["providers", p, section, name, "enabled"], undefined) as JsonObject, p);
      }
    }
    return raw;
  }
  const base = asObject(asObject(draft[section])[name]).enabled !== false;
  const value = enabled === base ? undefined : enabled;
  return prune(setIn(draft, ["providers", provider, section, name, "enabled"], value) as JsonObject, provider);
}

/** Per-provider overrides that switch things off on `provider` (for listing / undoing). */
export function overridesOn(draft: JsonObject, provider: string): { section: "functions" | "workflows"; name: string; what: string }[] {
  const out: { section: "functions" | "workflows"; name: string; what: string }[] = [];
  for (const section of ["functions", "workflows"] as const) {
    for (const [name, body] of Object.entries(asObject(getIn(draft, ["providers", provider, section])))) {
      const b = asObject(body);
      if (b.enabled === false) out.push({ section, name, what: "disabled" });
      if (section === "functions" && Array.isArray(b.events)) out.push({ section, name, what: "own triggers" });
    }
  }
  return out;
}

/** Remove empty mappings left under providers.<p> by the edits above. */
function prune(draft: JsonObject, provider: string): JsonObject {
  let raw: JsonObject = draft;
  for (const section of ["functions", "workflows"]) {
    const items = asObject(getIn(raw, ["providers", provider, section]));
    for (const [name, body] of Object.entries(items)) {
      if (!Object.keys(asObject(body)).length) raw = setIn(raw, ["providers", provider, section, name], undefined) as JsonObject;
    }
    if (getIn(raw, ["providers", provider, section]) !== undefined && !Object.keys(asObject(getIn(raw, ["providers", provider, section]))).length) {
      raw = setIn(raw, ["providers", provider, section], undefined) as JsonObject;
    }
  }
  if (getIn(raw, ["providers", provider]) !== undefined && !Object.keys(asObject(getIn(raw, ["providers", provider]))).length) {
    raw = setIn(raw, ["providers", provider], undefined) as JsonObject;
  }
  if (raw.providers !== undefined && !Object.keys(asObject(raw.providers)).length) raw = setIn(raw, ["providers"], undefined) as JsonObject;
  return raw;
}
