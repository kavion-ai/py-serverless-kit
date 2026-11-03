/**
 * `providers.<cloud>` blocks are merged over the top-level config when deploying to that cloud. For the *active*
 * provider, provider settings there (`providers.onprem.options.host`, `providers.onprem.region`,
 * `providers.onprem.provider.timeout`, ...) shadow what Overview shows and edits under `provider:`. Switching
 * providers used to leave such a copy behind, so an edited bind address or deploy method silently lost to it.
 */
import type { Json, JsonObject } from "./types";
import { asObject, getIn, isObject, setIn, str, type Path } from "./util";

/** ProviderConfig keys a `providers.<cloud>` block may write directly (config/loader.py `_PROVIDER_FIELDS`). */
export const PROVIDER_FIELDS = new Set([
  "region", "stage", "runtime", "memory", "timeout", "architecture", "environment", "tags", "iam",
  "log_retention_days", "options", "state", "terraform",
]);

function activeProvider(draft: JsonObject): string {
  return str(getIn(draft, ["provider", "name"]));
}

/** Drop `path`, then every parent left empty, up to (not including) `stop` levels. */
function removeIn(draft: JsonObject, path: Path, stop: number): JsonObject {
  let raw = setIn(draft, path, undefined) as JsonObject;
  for (let i = path.length - 1; i > stop; i--) {
    const parent = getIn(raw, path.slice(0, i));
    if (isObject(parent) && !Object.keys(parent).length) raw = setIn(raw, path.slice(0, i), undefined) as JsonObject;
    else break;
  }
  return raw;
}

/** Where `provider.<rest>` can be shadowed: `providers.<p>.<rest>` (shorthand) and `providers.<p>.provider.<rest>`. */
function shadowPaths(provider: string, rest: Path): Path[] {
  const out: Path[] = [["providers", provider, "provider", ...rest]];
  if (PROVIDER_FIELDS.has(String(rest[0]))) out.push(["providers", provider, ...rest]);
  return out;
}

/**
 * Editing `provider.<rest>` also removes the same setting from the active provider's `providers.<p>` block, so the
 * value typed in the studio is the one that deploys. Also clears a non-object ancestor there (`deploy: local`).
 */
export function clearShadow(draft: JsonObject, path: Path): JsonObject {
  if (path[0] !== "provider" || path.length < 2 || path[1] === "name") return draft;
  const provider = activeProvider(draft);
  if (!provider || !isObject(getIn(draft, ["providers", provider]))) return draft;
  let raw = draft;
  for (const target of shadowPaths(provider, path.slice(1))) {
    for (let depth = 3; depth <= target.length; depth++) {
      const value = getIn(raw, target.slice(0, depth));
      if (value === undefined) break;
      if (depth === target.length || !isObject(value)) {
        raw = removeIn(raw, target.slice(0, depth), 0);
        break;
      }
    }
  }
  return raw;
}

/** Provider settings in the active provider's `providers.<p>` block that override Overview, as dotted keys. */
export function providerShadows(draft: JsonObject): string[] {
  const provider = activeProvider(draft);
  const block = asObject(getIn(draft, ["providers", provider]));
  const keys: string[] = [];
  const walk = (value: Json | undefined, prefix: string) => {
    if (isObject(value) && Object.keys(value).length) {
      for (const [k, v] of Object.entries(value)) walk(v, prefix ? `${prefix}.${k}` : k);
    } else if (prefix) {
      keys.push(prefix);
    }
  };
  for (const [k, v] of Object.entries(block)) {
    if (k === "provider") walk(v, "");
    else if (PROVIDER_FIELDS.has(k)) walk(v, k);
  }
  return keys;
}

function mergeUnder(base: Json | undefined, top: Json | undefined): Json | undefined {
  if (top === undefined) return base;
  if (!isObject(base) || !isObject(top)) return top;
  const out: JsonObject = { ...base };
  for (const [k, v] of Object.entries(top)) out[k] = mergeUnder(base[k], v) as Json;
  return out;
}

/**
 * Move those settings into `provider:` and drop them from `providers.<p>`. The values shown in Overview win;
 * settings that only exist in the override are kept.
 */
export function absorbShadows(draft: JsonObject): JsonObject {
  const provider = activeProvider(draft);
  const block = asObject(getIn(draft, ["providers", provider]));
  let parked: JsonObject = asObject(block.provider);
  for (const [k, v] of Object.entries(block)) if (PROVIDER_FIELDS.has(k)) parked = { ...parked, [k]: v };
  const top = asObject(draft.provider);
  let raw = setIn(draft, ["provider"], mergeUnder(parked, top)) as JsonObject;
  for (const k of Object.keys(block)) {
    if (k === "provider" || PROVIDER_FIELDS.has(k)) raw = removeIn(raw, ["providers", provider, k], 0);
  }
  return raw;
}
