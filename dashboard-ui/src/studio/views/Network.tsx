import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "../api";
import { PageHeader } from "../components/Misc";
import { UsageList, usageFunctions } from "../components/ServerUsage";
import { href, navigate } from "../route";
import type { FirewallLevel, NetworkEdge, NetworkNode, OnPremUsage } from "../types";

/** Network map: every saved server and the connections each one has to accept (inbound) and open (outbound), drawn
 * from the firewall rules the project needs now (deploys, function groups, clusters, load balancers, services).
 * Click a machine to see its inbound and outbound connections and where it is used. */

const W = 900;
const BOX_W = 160;
const BOX_H = 48;
const SPECIAL_W = 150;
const SPECIAL_H = 40;
const LEVELS: FirewallLevel[] = ["required", "feature", "optional"];
const LEVEL_RANK: Record<FirewallLevel, number> = { required: 0, feature: 1, optional: 2 };
const LEVEL_DASH: Record<FirewallLevel, string | undefined> = { required: undefined, feature: "7 4", optional: "2 4" };
const LEVEL_HELP: Record<FirewallLevel, string> = {
  required: "it does not work without it",
  feature: "needed for that feature",
  optional: "pskit falls back to an SSH tunnel",
};
const SPECIAL_LABEL: Record<string, string> = {
  admin: "This machine (pskit)",
  users: "Users / clients",
  internet: "Internet",
};

interface Placed extends NetworkNode {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Edges between the same two machines in the same direction, merged into one line with every port. */
interface Link {
  from: string;
  to: string;
  ports: string[];
  level: FirewallLevel;
  rules: NetworkEdge[];
}

function layout(nodes: NetworkNode[]): { placed: Record<string, Placed>; height: number } {
  const machines = nodes.filter((n) => n.kind === "server" || n.kind === "host");
  const n = machines.length;
  // The machines on an ellipse between the sources: this machine and the users on the left, the internet on the right.
  const left = SPECIAL_W / 2 + 12;
  const rx = n <= 1 ? 0 : W / 2 - left - SPECIAL_W / 2 - BOX_W / 2 - 24;
  const ry = n <= 1 ? 0 : Math.min(300, Math.max(120, n * 30));
  const height = Math.max(380, 2 * ry + BOX_H + 70);
  const cx = W / 2;
  const cy = height / 2;
  const placed: Record<string, Placed> = {};
  machines.forEach((m, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(n, 1);
    placed[m.id] = { ...m, x: cx + rx * Math.cos(angle), y: cy + ry * Math.sin(angle), w: BOX_W, h: BOX_H };
  });
  const specials: Record<string, [number, number]> = {
    admin: [left, cy - 70],
    users: [left, cy + 70],
    internet: [W - left, cy],
  };
  for (const node of nodes) {
    if (node.kind in specials) {
      const [x, y] = specials[node.kind];
      placed[node.id] = { ...node, x, y, w: SPECIAL_W, h: SPECIAL_H };
    }
  }
  return { placed, height };
}

/** Distance from a box's center to its border along (dx, dy). */
function toBorder(p: Placed, dx: number, dy: number): number {
  const ax = Math.abs(dx) || 1e-6;
  const ay = Math.abs(dy) || 1e-6;
  const len = Math.hypot(dx, dy) || 1;
  return Math.min(p.w / 2 / ax, p.h / 2 / ay) * len + 4;
}

function curve(a: Placed, b: Placed) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  // Bend to the right of the direction of travel, so A→B and B→A are two separate lines.
  const bend = Math.min(60, len * 0.18);
  const cxp = (a.x + b.x) / 2 + (dy / len) * bend;
  const cyp = (a.y + b.y) / 2 - (dx / len) * bend;
  const sdx = cxp - a.x;
  const sdy = cyp - a.y;
  const sl = Math.hypot(sdx, sdy) || 1;
  const s = toBorder(a, sdx, sdy);
  const edx = b.x - cxp;
  const edy = b.y - cyp;
  const el = Math.hypot(edx, edy) || 1;
  const e = toBorder(b, edx, edy);
  const x1 = a.x + (sdx / sl) * s;
  const y1 = a.y + (sdy / sl) * s;
  const x2 = b.x - (edx / el) * e;
  const y2 = b.y - (edy / el) * e;
  return {
    d: `M ${x1.toFixed(1)} ${y1.toFixed(1)} Q ${cxp.toFixed(1)} ${cyp.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`,
    mx: 0.25 * x1 + 0.5 * cxp + 0.25 * x2,
    my: 0.25 * y1 + 0.5 * cyp + 0.25 * y2,
  };
}

function nodeLabel(n: NetworkNode): string {
  return SPECIAL_LABEL[n.kind] || n.id;
}

function clip(text: string, max: number): string {
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

function nodeColor(n: NetworkNode): string {
  if (n.kind === "admin") return "var(--accent)";
  if (n.kind === "users") return "var(--ok)";
  if (n.kind === "internet") return "var(--off)";
  if (n.kind === "host") return "var(--warn)";
  return n.uses ? "var(--info)" : "var(--line-strong)";
}

export function NetworkView({ rest }: { rest: string[] }) {
  const [data, setData] = useState<OnPremUsage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [levels, setLevels] = useState<Record<FirewallLevel, boolean>>({ required: true, feature: true, optional: true });
  const [showUnused, setShowUnused] = useState(true);
  const selected = rest[0] || null;
  const select = (id: string | null) => (id ? navigate("network", id) : navigate("network"));

  const load = useCallback(() => {
    setError(null);
    api.onpremServerUsage().then(setData, (exc: unknown) => setError(errorMessage(exc)));
  }, []);
  useEffect(load, [load]);

  const edges = useMemo(() => (data?.map.edges || []).filter((e) => levels[e.level]), [data, levels]);
  const nodes = useMemo(() => {
    const all = data?.map.nodes || [];
    const connected = new Set(edges.flatMap((e) => [e.from, e.to]));
    return all.filter((n) => {
      if (n.kind === "server" || n.kind === "host") return showUnused || n.uses > 0 || connected.has(n.id) || n.id === selected;
      return connected.has(n.id);
    });
  }, [data, edges, showUnused, selected]);
  const { placed, height } = useMemo(() => layout(nodes), [nodes]);
  const links = useMemo(() => {
    const out: Record<string, Link> = {};
    for (const e of edges) {
      if (e.from === e.to || !placed[e.from] || !placed[e.to]) continue;
      const key = `${e.from}\u0000${e.to}`;
      const link = (out[key] ||= { from: e.from, to: e.to, ports: [], level: e.level, rules: [] });
      const port = `${e.port}/${e.proto}`;
      if (!link.ports.includes(port)) link.ports.push(port);
      if (LEVEL_RANK[e.level] < LEVEL_RANK[link.level]) link.level = e.level;
      link.rules.push(e);
    }
    return Object.values(out);
  }, [edges, placed]);

  const sel = selected ? (data?.map.nodes || []).find((n) => n.id === selected) : undefined;
  const inbound = selected ? edges.filter((e) => e.to === selected) : [];
  const outbound = selected ? edges.filter((e) => e.from === selected) : [];
  const uses = selected ? data?.servers[selected] || [] : [];
  const unused = (data?.map.nodes || []).filter((n) => n.kind === "server" && !n.uses);

  return (
    <div className="page">
      <PageHeader
        title="Network map"
        subtitle="Every on-prem server and the connections it has to accept (inbound) and open (outbound) for this project: deploys, function groups, clusters, load balancers and services. Click a machine for its details."
        actions={
          <button type="button" className="btn" onClick={load}>
            Refresh
          </button>
        }
      />
      {error && <div className="form-error">{error}</div>}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && (
        <>
          {data.map.error && <div className="form-warn">{data.map.error}</div>}
          <div className="card card-pad row-between wrap net-toolbar">
            <span className="row-gap wrap">
              {LEVELS.map((lv) => (
                <label key={lv} className="row-gap small" title={LEVEL_HELP[lv]}>
                  <input type="checkbox" checked={levels[lv]} onChange={(e) => setLevels((l) => ({ ...l, [lv]: e.target.checked }))} />
                  <svg width="34" height="10" aria-hidden="true">
                    <line x1="2" y1="5" x2="32" y2="5" stroke="var(--text)" strokeWidth="2" strokeDasharray={LEVEL_DASH[lv]} />
                  </svg>
                  {lv}
                </label>
              ))}
              <label className="row-gap small">
                <input type="checkbox" checked={showUnused} onChange={(e) => setShowUnused(e.target.checked)} />
                servers not used anywhere ({unused.length})
              </label>
            </span>
            <span className="row-gap small">
              <span className="net-key" style={{ background: "var(--ok)" }} /> inbound to the selected machine
              <span className="net-key" style={{ background: "var(--info)" }} /> outbound from it
            </span>
          </div>

          {!nodes.length ? (
            <div className="card card-pad">
              <p className="muted">
                No servers and no connections yet. Save a server under <a href={href("resources")}>Resources → Servers</a>, then deploy to it, create a cluster, a load balancer or a
                service there; this map follows.
              </p>
            </div>
          ) : (
            <div className="net-layout">
              <div className="card net-canvas">
                <svg viewBox={`0 0 ${W} ${height}`} width="100%" role="img" aria-label="Connections between the project's machines" onClick={() => select(null)}>
                  <defs>
                    {["line", "in", "out"].map((k) => (
                      <marker key={k} id={`net-arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill={k === "in" ? "var(--ok)" : k === "out" ? "var(--info)" : "var(--line-strong)"} />
                      </marker>
                    ))}
                  </defs>
                  {links.map((l) => {
                    const a = placed[l.from];
                    const b = placed[l.to];
                    const c = curve(a, b);
                    const isIn = selected === l.to;
                    const isOut = selected === l.from;
                    const faded = selected && !isIn && !isOut;
                    const color = isIn ? "var(--ok)" : isOut ? "var(--info)" : "var(--line-strong)";
                    const label = clip(l.ports.join(", "), 26);
                    return (
                      <g key={`${l.from}>${l.to}`} opacity={faded ? 0.15 : 1}>
                        <path d={c.d} fill="none" stroke={color} strokeWidth={isIn || isOut ? 2.2 : 1.5} strokeDasharray={LEVEL_DASH[l.level]} markerEnd={`url(#net-arrow-${isIn ? "in" : isOut ? "out" : "line"})`}>
                          <title>{`${nodeLabel(a)} → ${nodeLabel(b)}\n${l.rules.map((r) => `${r.port}/${r.proto} (${r.level}): ${r.why}`).join("\n")}`}</title>
                        </path>
                        {(!selected || isIn || isOut) && (
                          <g>
                            <rect x={c.mx - label.length * 3.1 - 5} y={c.my - 8} width={label.length * 6.2 + 10} height={15} rx={7} fill="var(--panel)" stroke={color} strokeWidth={0.8} />
                            <text x={c.mx} y={c.my + 3} fontSize={10.5} textAnchor="middle" fill="var(--text)" fontFamily="var(--mono)">
                              {label}
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}
                  {Object.values(placed).map((p) => {
                    const active = p.id === selected;
                    const color = nodeColor(p);
                    const machine = p.kind === "server" || p.kind === "host";
                    const sub = machine ? p.address || (p.saved ? "" : "not a saved server") : p.kind === "admin" ? "SSH, logs, tests" : p.kind === "users" ? "your functions' callers" : "downloads, images";
                    return (
                      <g
                        key={p.id}
                        className="net-node"
                        transform={`translate(${p.x - p.w / 2}, ${p.y - p.h / 2})`}
                        onClick={(e) => {
                          e.stopPropagation();
                          select(active ? null : p.id);
                        }}
                        role="button"
                        aria-label={`${nodeLabel(p)}${p.uses ? `, used in ${p.uses} places` : ""}`}
                      >
                        <rect width={p.w} height={p.h} rx={machine ? 10 : p.h / 2} fill={active ? "var(--accent-soft)" : "var(--panel)"} stroke={active ? "var(--accent)" : color} strokeWidth={active ? 2.4 : 1.6} strokeDasharray={p.kind === "server" && !p.uses ? "4 3" : p.kind === "host" ? "2 3" : undefined} />
                        {machine && <rect width={5} height={p.h} rx={2} fill={color} />}
                        <text x={machine ? 14 : p.w / 2} y={machine ? 20 : 17} fontSize={13} fontWeight={700} fill="var(--text)" textAnchor={machine ? "start" : "middle"}>
                          {clip(nodeLabel(p), p.kind === "server" ? 14 : 20)}
                        </text>
                        <text x={machine ? 14 : p.w / 2} y={machine ? 37 : 31} fontSize={11} fill="var(--muted)" textAnchor={machine ? "start" : "middle"} fontFamily={machine ? "var(--mono)" : undefined}>
                          {clip(sub, 22)}
                        </text>
                        {p.kind === "server" && (
                          <text x={p.w - 10} y={19} fontSize={10.5} textAnchor="end" fill={p.uses ? "var(--info)" : "var(--muted)"} fontWeight={600}>
                            {p.uses ? `×${p.uses}` : "unused"}
                          </text>
                        )}
                        <title>{[nodeLabel(p), p.address, ...p.roles].filter(Boolean).join("\n")}</title>
                      </g>
                    );
                  })}
                </svg>
              </div>

              <aside className="card card-pad net-side">
                {!sel ? (
                  <>
                    <h3>Machines</h3>
                    <p className="muted small">Pick one on the map or here.</p>
                    <ul className="net-list">
                      {(data.map.nodes || []).map((n) => {
                        const ins = edges.filter((e) => e.to === n.id).length;
                        const outs = edges.filter((e) => e.from === n.id).length;
                        return (
                          <li key={n.id}>
                            <button type="button" className="btn btn-ghost btn-sm net-pick" onClick={() => select(n.id)}>
                              <span className="net-key" style={{ background: nodeColor(n) }} />
                              <b className={n.kind === "server" || n.kind === "host" ? "mono" : ""}>{nodeLabel(n)}</b>
                              <span className="muted small">
                                {" "}
                                ↓{ins} ↑{outs}
                                {n.kind === "server" && !n.uses ? " · not used anywhere" : n.roles.length ? ` · ${clip(n.roles.join(", "), 40)}` : ""}
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                ) : (
                  <>
                    <div className="row-between">
                      <h3 className={sel.kind === "server" || sel.kind === "host" ? "mono" : ""}>{nodeLabel(sel)}</h3>
                      <button type="button" className="btn btn-sm" onClick={() => select(null)}>
                        All machines
                      </button>
                    </div>
                    {sel.address && <div className="muted small mono">{sel.address}</div>}
                    {sel.kind === "host" && <p className="form-warn small">Not a saved server: an address pskit knows from a deploy or a service. Save it to manage it here.</p>}
                    <ConnTable title="Inbound — accept" peer="from" rules={inbound} />
                    <ConnTable title="Outbound — open" peer="to" rules={outbound} />
                    {(sel.kind === "server" || sel.kind === "host") && (
                      <>
                        <h4>Used in</h4>
                        {usageFunctions(uses).length > 0 && (
                          <p className="small">
                            Functions:{" "}
                            <span className="chips">
                              {usageFunctions(uses).map((f) => (
                                <a key={f} className="chip" href={href("functions", f)}>
                                  {f}
                                </a>
                              ))}
                            </span>
                          </p>
                        )}
                        <UsageList uses={uses} compact />
                      </>
                    )}
                  </>
                )}
              </aside>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ConnTable({ title, peer, rules }: { title: string; peer: "from" | "to"; rules: NetworkEdge[] }) {
  return (
    <>
      <h4>
        {title} <span className="muted small">({rules.length})</span>
      </h4>
      {!rules.length ? (
        <p className="muted small">None.</p>
      ) : (
        <ul className="net-conn">
          {rules.map((r, i) => {
            const other = r[peer];
            return (
              <li key={i}>
                <div className="row-gap wrap">
                  <span className="muted small">{peer}</span>
                  <button type="button" className="btn btn-ghost btn-sm mono" onClick={() => navigate("network", other)}>
                    {SPECIAL_LABEL[other] || other}
                  </button>
                  <span className="mono small">
                    {r.port}/{r.proto}
                  </span>
                  <span className={`badge ${r.level === "required" ? "badge-err" : r.level === "feature" ? "badge-warn" : "badge-off"}`} title={LEVEL_HELP[r.level]}>
                    {r.level}
                  </span>
                </div>
                <div className="muted small">{r.why}</div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
