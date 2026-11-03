import type { KeyboardEvent } from "react";
import type { BalancerKind, LbAlgorithm } from "../types";
import { FormRow, NumberInput } from "./Forms";

/**
 * Load balancing algorithms: a picker grouped into static and dynamic, each card with a small looping animation of
 * how it spreads requests plus the pros, cons and "best for" the API sends. Only the animations live here; every
 * text about an algorithm comes from `GET /api/onprem-balancers` → `algorithms`.
 */

const KINDS: { kind: BalancerKind; label: string; explain: string }[] = [
  { kind: "static", label: "Static", explain: "A fixed rule picks the server. Nothing is measured while requests run." },
  { kind: "dynamic", label: "Dynamic", explain: "Decided per request from live load: requests in progress and response times." },
];

export function KindBadge({ kind }: { kind: BalancerKind | string }) {
  return (
    <span className={`badge ${kind === "dynamic" ? "badge-accent" : "badge-info"}`} title={KINDS.find((k) => k.kind === kind)?.explain}>
      {kind === "dynamic" ? "Dynamic" : "Static"}
    </span>
  );
}

/** The label of algorithm `name`, or a readable form of the name when the catalog is not loaded (yet). */
export function algorithmLabel(algorithms: LbAlgorithm[] | undefined, name: string | null | undefined): string {
  if (!name) return "";
  const found = algorithms?.find((a) => a.name === name);
  if (found) return found.label;
  const text = name.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function AlgorithmPicker({
  algorithms,
  value,
  onChange,
  defaultAlgorithm,
}: {
  algorithms: LbAlgorithm[];
  value: string;
  onChange: (name: string) => void;
  /** Marked "default": what a load balancer uses when none is chosen. */
  defaultAlgorithm?: string;
}) {
  const choose = (name: string) => (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onChange(name);
    }
  };
  return (
    <div className="lb-picker" role="radiogroup" aria-label="Load balancing algorithm">
      {KINDS.map(({ kind, label, explain }) => {
        const items = algorithms.filter((a) => (a.kind === "dynamic" ? "dynamic" : "static") === kind);
        if (!items.length) return null;
        return (
          <section key={kind} className="lb-group">
            <div className="lb-group-head">
              <KindBadge kind={kind} />
              <b>{label}</b>
              <span className="muted small">{explain}</span>
            </div>
            <div className="lb-grid">
              {items.map((a) => {
                const selected = a.name === value;
                return (
                  <div
                    key={a.name}
                    role="radio"
                    aria-checked={selected}
                    tabIndex={0}
                    className={`lb-card${selected ? " selected" : ""}`}
                    onClick={() => onChange(a.name)}
                    onKeyDown={choose(a.name)}
                  >
                    <div className="lb-card-head">
                      <b>{a.label}</b>
                      {a.name === defaultAlgorithm && <span className="badge badge-off">default</span>}
                      <span className="lb-check" aria-hidden="true">
                        {selected ? "✓" : ""}
                      </span>
                    </div>
                    <AlgorithmAnimation name={a.name} />
                    <p className="small lb-summary">{a.summary}</p>
                    <ul className="lb-list lb-pros" aria-label="Pros">
                      {a.pros.map((p, i) => (
                        <li key={p} style={{ animationDelay: `${i * 70}ms` }}>
                          {p}
                        </li>
                      ))}
                    </ul>
                    <ul className="lb-list lb-cons" aria-label="Cons">
                      {a.cons.map((c, i) => (
                        <li key={c} style={{ animationDelay: `${(a.pros.length + i) * 70}ms` }}>
                          {c}
                        </li>
                      ))}
                    </ul>
                    {a.best_for && (
                      <div className="small muted">
                        <b>Best for:</b> {a.best_for}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ weights

/** Whether an algorithm uses per-server weights: always, optionally, or not at all. */
export function weightsUse(algorithm: string): "required" | "optional" | null {
  if (algorithm === "weighted_round_robin") return "required";
  if (algorithm === "least_connections" || algorithm === "least_time") return "optional";
  return null;
}

export function weightsValid(weights: Record<string, number>): boolean {
  return Object.values(weights).every((w) => Number.isInteger(w) && w >= 1 && w <= 100);
}

/** The weights to send: only the given servers, and none for an algorithm that ignores them. */
export function weightsFor(algorithm: string, weights: Record<string, number>, servers: string[]): Record<string, number> | undefined {
  if (!weightsUse(algorithm)) return undefined;
  const out: Record<string, number> = {};
  for (const s of servers) if (weights[s] !== undefined) out[s] = weights[s];
  return out;
}

/** Weight 1..100 per server (empty: 1). Shown for weighted round robin, and folded for the dynamic algorithms. */
export function WeightsEditor({
  algorithm,
  servers,
  value,
  onChange,
}: {
  algorithm: string;
  servers: string[];
  value: Record<string, number>;
  onChange: (weights: Record<string, number>) => void;
}) {
  const use = weightsUse(algorithm);
  if (!use) return null;
  if (!servers.length)
    return <p className="muted small">Weights: no servers to weigh yet (they come from the clusters and projects that use it).</p>;
  const set = (server: string, w: number | undefined) => {
    const next = { ...value };
    if (w === undefined) delete next[server];
    else next[server] = w;
    onChange(next);
  };
  const editor = (
    <div className="row-gap wrap">
      {servers.map((s) => (
        <FormRow key={s} label={<span className="mono">{s}</span>} inline>
          <NumberInput value={value[s]} min={1} max={100} integer placeholder="1" onChange={(w) => set(s, w)} />
        </FormRow>
      ))}
    </div>
  );
  const help =
    use === "required"
      ? "A server with weight 3 gets three requests for every one a weight 1 server gets. 1..100, empty: 1."
      : "Optional: a bigger weight makes the server look less busy, so it gets more of the load. 1..100, empty: 1.";
  if (use === "required")
    return (
      <FormRow label="Weights" help={help}>
        {editor}
      </FormRow>
    );
  return (
    <details className="lb-weights" open={Object.keys(value).length > 0}>
      <summary className="small">Weights (optional)</summary>
      <p className="muted small">{help}</p>
      {editor}
    </details>
  );
}

// ------------------------------------------------------------------------------------------------ animations

interface Spec {
  /** Clients on the left (colored, labeled); none: anonymous requests arrive from the left edge. */
  clients?: { label: string; color: string }[];
  /** Per server: label, extra note on its right, a bigger box. */
  servers: { label: string; note?: string; noteColor?: string; big?: boolean }[];
  /** One request per slot: its server and (with clients) the client that sent it. */
  requests: { to: number; client?: number }[];
  /** Requests in progress per server before each slot (least connections): drawn as queue bars. */
  queues?: number[][];
  slot?: number;
}

const C1 = "var(--info)";
const C2 = "var(--warn)";
const C3 = "var(--ok)";
const QUEUE_MAX = 4;

const SPECS: Record<string, Spec> = {
  round_robin: {
    servers: [{ label: "srv 1" }, { label: "srv 2" }, { label: "srv 3" }],
    requests: [{ to: 0 }, { to: 1 }, { to: 2 }, { to: 0 }, { to: 1 }, { to: 2 }],
  },
  sticky_round_robin: {
    clients: [
      { label: "user A", color: C1 },
      { label: "user B", color: C2 },
      { label: "user C", color: C3 },
    ],
    servers: [{ label: "srv 1" }, { label: "srv 2" }, { label: "srv 3" }],
    requests: [
      { client: 0, to: 0 },
      { client: 1, to: 1 },
      { client: 0, to: 0 },
      { client: 2, to: 2 },
      { client: 1, to: 1 },
      { client: 0, to: 0 },
    ],
  },
  weighted_round_robin: {
    servers: [{ label: "srv 1", note: "×3", big: true }, { label: "srv 2", note: "×1" }, { label: "srv 3", note: "×1" }],
    requests: [{ to: 0 }, { to: 1 }, { to: 0 }, { to: 2 }, { to: 0 }],
  },
  ip_hash: {
    clients: [
      { label: ".12", color: C1 },
      { label: ".40", color: C2 },
      { label: ".77", color: C3 },
    ],
    servers: [{ label: "srv 1" }, { label: "srv 2" }, { label: "srv 3" }],
    requests: [
      { client: 0, to: 2 },
      { client: 1, to: 0 },
      { client: 0, to: 2 },
      { client: 2, to: 1 },
      { client: 1, to: 0 },
      { client: 2, to: 1 },
    ],
  },
  least_connections: {
    servers: [{ label: "srv 1" }, { label: "srv 2" }, { label: "srv 3" }],
    queues: [
      [3, 1, 2],
      [3, 2, 1],
      [2, 2, 2],
      [1, 3, 2],
      [2, 3, 1],
      [3, 1, 2],
    ],
    requests: [{ to: 1 }, { to: 2 }, { to: 0 }, { to: 0 }, { to: 2 }, { to: 1 }],
  },
  least_time: {
    servers: [
      { label: "srv 1", note: "20ms", noteColor: "var(--ok)" },
      { label: "srv 2", note: "80ms", noteColor: "var(--warn)" },
      { label: "srv 3", note: "300ms", noteColor: "var(--err)" },
    ],
    requests: [{ to: 0 }, { to: 0 }, { to: 1 }, { to: 0 }, { to: 0 }, { to: 1 }, { to: 0 }, { to: 2 }],
  },
};

const W = 220;
const H = 80;
const LB = { x: 74, y: 30, w: 30, h: 20 };
const LB_C = { x: LB.x + LB.w / 2, y: LB.y + LB.h / 2 };
const SRV_X = 138;
const SRV_W = 46;
const ROWS = [14, 40, 66];

const pct = (v: number) => `${Math.min(100, Math.max(0, v * 100)).toFixed(2)}%`;
const tr = (x: number, y: number) => `transform: translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;

/** A looping SVG of how the algorithm spreads requests (CSS keyframes; still under prefers-reduced-motion). */
export function AlgorithmAnimation({ name }: { name: string }) {
  const spec = SPECS[name];
  if (!spec) return null;
  const id = `lbx-${name.replace(/[^a-z0-9_-]/gi, "")}`;
  const n = spec.requests.length;
  const slot = spec.slot ?? 0.8;
  const duration = `${(n * slot).toFixed(2)}s`;
  const len = 1 / n;

  // Where each dot lands: stacked inside its server box.
  const seen = [0, 0, 0];
  const dots = spec.requests.map((r, i) => {
    const k = seen[r.to]++;
    const start = spec.clients && r.client !== undefined ? { x: 34, y: ROWS[r.client] } : { x: 4, y: LB_C.y };
    const total = spec.requests.filter((x) => x.to === r.to).length;
    const dy = total <= 3 ? 0 : (Math.floor(k / 3) ? 3.5 : -2.5) * (spec.servers[r.to].big ? 1.6 : 1);
    const end = { x: SRV_X + 24 + (k % 3) * 7, y: ROWS[r.to] + dy };
    const color = spec.clients && r.client !== undefined ? spec.clients[r.client].color : "var(--accent)";
    const t0 = i * len;
    return { i, to: r.to, start, end, color, t0, arrive: t0 + 0.8 * len };
  });

  let css = "";
  for (const d of dots) {
    const frames = [`0% { ${tr(d.start.x, d.start.y)}; opacity: 0; }`];
    if (d.t0 > 0) frames.push(`${pct(d.t0)} { ${tr(d.start.x, d.start.y)}; opacity: 0; }`);
    frames.push(`${pct(d.t0 + 0.08 * len)} { opacity: 1; }`);
    frames.push(`${pct(d.t0 + 0.42 * len)} { ${tr(LB_C.x, LB_C.y)}; }`);
    frames.push(`${pct(d.arrive)} { ${tr(d.end.x, d.end.y)}; opacity: 1; }`);
    frames.push(`${pct(d.t0 + 0.98 * len)} { opacity: 0; }`);
    frames.push(`100% { ${tr(d.end.x, d.end.y)}; opacity: 0; }`);
    css += `@keyframes ${id}-d${d.i} { ${frames.join(" ")} }\n`;
    css += `.${id}-d${d.i} { ${tr(d.end.x, d.end.y)}; animation: ${id}-d${d.i} ${duration} ease-in-out infinite; }\n`;
  }
  spec.servers.forEach((_, s) => {
    const frames = ["0% { opacity: 0; }"];
    for (const d of dots.filter((x) => x.to === s)) {
      frames.push(`${pct(d.arrive - 0.02 * len)} { opacity: 0; }`, `${pct(d.arrive)} { opacity: 0.32; }`, `${pct(d.arrive + 0.18 * len)} { opacity: 0; }`);
    }
    frames.push("100% { opacity: 0; }");
    css += `@keyframes ${id}-f${s} { ${frames.join(" ")} }\n`;
    css += `.${id}-f${s} { opacity: 0; animation: ${id}-f${s} ${duration} linear infinite; }\n`;
    if (spec.queues) {
      const q = spec.queues;
      const scale = (v: number) => `transform: scaleX(${(Math.min(QUEUE_MAX, v) / QUEUE_MAX).toFixed(3)})`;
      const qf: string[] = [];
      dots.forEach((d) => {
        const before = q[d.i][s];
        const after = before + (d.to === s ? 1 : 0);
        qf.push(`${pct(d.t0)} { ${scale(before)}; }`, `${pct(d.arrive - 0.01 * len)} { ${scale(before)}; }`, `${pct(d.arrive)} { ${scale(after)}; }`);
      });
      qf.push(`100% { ${scale(q[0][s])}; }`);
      css += `@keyframes ${id}-q${s} { ${qf.join(" ")} }\n`;
      css += `.${id}-q${s} { ${scale(q[0][s])}; animation: ${id}-q${s} ${duration} ease-out infinite; }\n`;
    }
  });

  return (
    <svg className="lb-anim" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`How ${name.replace(/_/g, " ")} spreads requests`}>
      <style>{css}</style>
      {spec.clients ? (
        spec.clients.map((c, i) => (
          <g key={c.label}>
            <rect x={2} y={ROWS[i] - 7} width={32} height={14} rx={7} style={{ fill: "var(--panel)", stroke: c.color }} />
            <text x={18} y={ROWS[i] + 3} textAnchor="middle" className="lb-anim-text">
              {c.label}
            </text>
            <line x1={34} y1={ROWS[i]} x2={LB.x} y2={LB_C.y} className="lb-anim-link" />
          </g>
        ))
      ) : (
        <line x1={4} y1={LB_C.y} x2={LB.x} y2={LB_C.y} className="lb-anim-link" />
      )}
      {spec.servers.map((_, s) => (
        <line key={s} x1={LB.x + LB.w} y1={LB_C.y} x2={SRV_X} y2={ROWS[s]} className="lb-anim-link" />
      ))}
      <rect x={LB.x} y={LB.y} width={LB.w} height={LB.h} rx={4} style={{ fill: "var(--accent-soft)", stroke: "var(--accent)" }} />
      <text x={LB_C.x} y={LB_C.y + 3.5} textAnchor="middle" className="lb-anim-text" style={{ fill: "var(--accent)", fontWeight: 700 }}>
        LB
      </text>
      {spec.servers.map((srv, s) => {
        const h = srv.big ? 26 : 18;
        const y = ROWS[s] - h / 2;
        return (
          <g key={srv.label}>
            <rect x={SRV_X} y={y} width={SRV_W} height={h} rx={3} style={{ fill: "var(--panel)", stroke: "var(--line-strong)" }} />
            <rect x={SRV_X} y={y} width={SRV_W} height={h} rx={3} className={`${id}-f${s}`} style={{ fill: "var(--accent)" }} />
            <text x={SRV_X + 3} y={ROWS[s] + 3} className="lb-anim-text">
              {srv.label.replace("srv ", "#")}
            </text>
            {srv.note && (
              <text x={SRV_X + SRV_W + 3} y={ROWS[s] + 3} className="lb-anim-text" style={{ fill: srv.noteColor || "var(--text)", fontWeight: 700 }}>
                {srv.note}
              </text>
            )}
            {spec.queues && (
              <>
                <rect x={SRV_X + SRV_W + 4} y={ROWS[s] - 3} width={28} height={6} rx={2} style={{ fill: "var(--line)" }} />
                <rect x={SRV_X + SRV_W + 4} y={ROWS[s] - 3} width={28} height={6} rx={2} className={`lb-anim-queue ${id}-q${s}`} style={{ fill: "var(--warn)" }} />
              </>
            )}
          </g>
        );
      })}
      {dots.map((d) => (
        <circle key={d.i} cx={0} cy={0} r={3.4} className={`${id}-d${d.i}`} style={{ fill: d.color }} />
      ))}
    </svg>
  );
}
