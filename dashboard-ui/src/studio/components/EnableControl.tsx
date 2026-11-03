import { isEnabled, setEnabledOn } from "../compat";
import { useStudio } from "../store";
import type { JsonObject } from "../types";
import { asObject } from "../util";

type Mode = "on" | "off-here" | "off";

/**
 * Deploy a function / workflow everywhere, skip it on the current provider only
 * (`providers.<cloud>.<section>.<name>.enabled: false`), or skip it everywhere (`enabled: false`).
 */
export function EnableControl({ section, name, compact }: { section: "functions" | "workflows"; name: string; compact?: boolean }) {
  const { draft, replace, providerName, provider } = useStudio();
  const everywhere = asObject(asObject(draft[section])[name]).enabled !== false;
  const here = isEnabled(draft, providerName, section, name);
  const mode: Mode = !everywhere ? "off" : !here ? "off-here" : "on";
  const label = provider?.display_name || providerName;
  const change = (next: Mode) => {
    let raw: JsonObject = setEnabledOn(draft, null, section, name, next !== "off");
    if (next === "off-here") raw = setEnabledOn(raw, providerName, section, name, false);
    replace(raw);
  };
  return (
    <select
      className={`select ${compact ? "select-sm" : ""} enable-select enable-${mode}`}
      value={mode}
      aria-label={`Deploy ${name}`}
      title={mode === "on" ? "Deployed" : mode === "off-here" ? `Kept in pskit.yml but not deployed to ${label}` : "Kept in pskit.yml but never deployed"}
      onChange={(e) => change(e.target.value as Mode)}
      onClick={(e) => e.stopPropagation()}
    >
      <option value="on">● Enabled</option>
      <option value="off-here">◐ Disabled on {label}</option>
      <option value="off">○ Disabled everywhere</option>
    </select>
  );
}
