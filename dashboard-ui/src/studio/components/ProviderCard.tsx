import type { ProviderMeta } from "../types";

const CAP_LABEL: Record<string, string> = {
  http: "HTTP",
  schedule: "Schedule",
  queue: "Queue",
  storage: "Storage",
  topic: "Topic",
  workflow_native: "Native workflows",
};

export function capabilityLabel(cap: string): string {
  return CAP_LABEL[cap] || cap;
}

export function ProviderCards({
  providers,
  value,
  onSelect,
}: {
  providers: ProviderMeta[];
  value: string;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="provider-grid" role="radiogroup" aria-label="Provider">
      {providers.map((p) => (
        <button
          key={p.name}
          type="button"
          role="radio"
          aria-checked={p.name === value}
          className={p.name === value ? "provider-card active" : "provider-card"}
          onClick={() => onSelect(p.name)}
        >
          <span className="provider-head">
            <span className={`provider-mark pm-${p.name}`} aria-hidden="true">
              {p.display_name.slice(0, 1)}
            </span>
            <span className="grow">
              <b>{p.display_name}</b>
              <span className="muted small mono">{p.name}</span>
            </span>
            {p.tier !== "stable" && <span className={`badge badge-${p.tier === "beta" ? "info" : "warn"}`}>{p.tier}</span>}
          </span>
          <span className="chips">
            {["http", "schedule", "queue", "storage", "topic", "smtp", "workflow_native"].map((cap) => (
              <span key={cap} className={p.capabilities.includes(cap) ? "chip chip-accent" : "chip chip-off"} title={p.capabilities.includes(cap) ? "supported" : "not supported"}>
                {capabilityLabel(cap)}
              </span>
            ))}
          </span>
        </button>
      ))}
    </div>
  );
}
