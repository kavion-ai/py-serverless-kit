import { Section, Toggle } from "./Forms";
import type { Json, JsonObject, ProviderMeta } from "../types";
import { asObject } from "../util";

export type MonitoringKind = "logs" | "metrics";

/** The effective switch: the function's own value, else provider.monitoring, else on. */
export function monitoringOn(fnMonitoring: Json | undefined, providerMonitoring: Json | undefined, kind: MonitoringKind): boolean {
  for (const source of [fnMonitoring, providerMonitoring]) {
    if (typeof source === "boolean") return source;
    const v = asObject(source)[kind];
    if (typeof v === "boolean") return v;
  }
  return true;
}

/**
 * `functions.<name>.monitoring` after switching `kind` to `on`. A value equal to the inherited one is dropped,
 * and so is the block once it is empty (undefined), so pskit.yml only keeps what differs from the defaults.
 */
export function setMonitoring(fnMonitoring: Json | undefined, providerMonitoring: Json | undefined, kind: MonitoringKind, on: boolean): JsonObject | undefined {
  const current: JsonObject =
    typeof fnMonitoring === "boolean" ? { logs: fnMonitoring, metrics: fnMonitoring } : { ...asObject(fnMonitoring) };
  const inherited = monitoringOn(undefined, providerMonitoring, kind);
  if (on === inherited) delete current[kind];
  else current[kind] = on;
  return Object.keys(current).length ? current : undefined;
}

/** Function editor: the logs / metrics services the provider creates next to the function (on by default). */
export function LogsMetricsSection({
  value,
  providerMonitoring,
  provider,
  onChange,
}: {
  value: Json | undefined;
  providerMonitoring: Json | undefined;
  provider: ProviderMeta | undefined;
  onChange: (next: JsonObject | undefined) => void;
}) {
  const info = provider?.monitoring;
  const controls = new Set(info?.controls || []);
  const logs = monitoringOn(value, providerMonitoring, "logs");
  const metrics = monitoringOn(value, providerMonitoring, "metrics");
  const off = [!logs && "logs", !metrics && "metrics"].filter(Boolean).join(" and ");
  const row = (kind: MonitoringKind, on: boolean, label: string) => (
    <li className="stack">
      <Toggle checked={on} onChange={(v) => onChange(setMonitoring(value, providerMonitoring, kind, v))} label={<b>{label}</b>} />
      <span className="muted small">
        {info?.[kind] || "The provider's own service."}
        {provider && !controls.has(kind) && " Built into the platform: switching it off has no effect here (validation warns)."}
      </span>
    </li>
  );
  return (
    <Section title="Logs & metrics" defaultOpen={!!off} hint={off ? `${off} off` : "on (default)"}>
      <p className="muted small">
        Services {provider ? provider.display_name : "the provider"} sets up next to the function. Both are on by default; switch one off for
        a function that does not need it (less cost and noise). The default for every function is <code className="mono">provider.monitoring</code>;
        this writes <code className="mono">functions.&lt;name&gt;.monitoring</code>. Package and Deploy list every resource with what it is for.
      </p>
      <ul className="bullets plain">
        {row("logs", logs, "Logs")}
        {row("metrics", metrics, "Metrics & tracing")}
      </ul>
    </Section>
  );
}
