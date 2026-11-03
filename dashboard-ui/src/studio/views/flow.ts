import type { JsonObject } from "../types";
import { asArray, asObject, str } from "../util";

export interface FlowEdge {
  from: string;
  to: string;
  label?: string;
  kind: "next" | "choice" | "default" | "catch";
}

export interface FlowNode {
  name: string;
  type: string;
  x: number;
  y: number;
  terminal: boolean;
  unreachable: boolean;
}

export const NODE_W = 184;
export const NODE_H = 52;
const GAP_X = 48;
const GAP_Y = 64;

export function edgesOf(def: JsonObject): FlowEdge[] {
  const out: FlowEdge[] = [];
  for (const [name, raw] of Object.entries(asObject(def.states))) {
    const st = asObject(raw);
    if (typeof st.next === "string" && st.next) out.push({ from: name, to: st.next, kind: "next" });
    asArray(st.choices).forEach((c, i) => {
      const next = str(asObject(c).next);
      if (next) out.push({ from: name, to: next, kind: "choice", label: ruleLabel(asObject(c)) || `rule ${i + 1}` });
    });
    if (typeof st.default === "string" && st.default) out.push({ from: name, to: st.default, kind: "default", label: "default" });
    asArray(st.catch).forEach((c) => {
      const next = str(asObject(c).next);
      if (next) out.push({ from: name, to: next, kind: "catch", label: `catch ${asArray(asObject(c).errors).map((e) => str(e)).join("|") || "*"}` });
    });
  }
  return out;
}

export function ruleLabel(rule: JsonObject): string {
  if (Array.isArray(rule.and)) return rule.and.map((r) => ruleLabel(asObject(r))).join(" and ");
  if (Array.isArray(rule.or)) return rule.or.map((r) => ruleLabel(asObject(r))).join(" or ");
  if (rule.not) return `not (${ruleLabel(asObject(rule.not))})`;
  const variable = str(rule.variable, "$");
  for (const [k, v] of Object.entries(rule)) {
    if (k === "variable" || k === "next") continue;
    return `${variable.replace(/^\$\./, "")} ${k} ${JSON.stringify(v)}`;
  }
  return "";
}

/** Layered top-down layout: rank = longest acyclic path from start_at. */
export function layout(def: JsonObject): { nodes: FlowNode[]; edges: FlowEdge[]; width: number; height: number } {
  const states = asObject(def.states);
  const names = Object.keys(states);
  const edges = edgesOf(def).filter((e) => e.to in states);
  const start = str(def.start_at);
  const rank = new Map<string, number>();
  const out = new Map<string, string[]>();
  names.forEach((n) => out.set(n, []));
  edges.forEach((e) => out.get(e.from)?.push(e.to));

  // DFS to find back edges, then longest path on the remaining DAG.
  const back = new Set<string>();
  const color = new Map<string, number>();
  const visit = (n: string) => {
    color.set(n, 1);
    for (const m of out.get(n) || []) {
      if (color.get(m) === 1) back.add(`${n}→${m}`);
      else if (!color.get(m)) visit(m);
    }
    color.set(n, 2);
  };
  if (start in states) visit(start);
  const reachable = new Set(Array.from(color.keys()));
  names.forEach((n) => {
    if (!color.get(n)) visit(n);
  });

  const order: string[] = [];
  const seen = new Set<string>();
  const topo = (n: string) => {
    if (seen.has(n)) return;
    seen.add(n);
    for (const m of out.get(n) || []) if (!back.has(`${n}→${m}`)) topo(m);
    order.unshift(n);
  };
  if (start in states) topo(start);
  names.forEach(topo);
  order.forEach((n) => {
    if (!rank.has(n)) rank.set(n, 0);
    for (const m of out.get(n) || []) {
      if (back.has(`${n}→${m}`)) continue;
      rank.set(m, Math.max(rank.get(m) ?? 0, (rank.get(n) ?? 0) + 1));
    }
  });
  // Unreachable states go in their own column on the right.
  const rows = new Map<number, string[]>();
  const orphans: string[] = [];
  for (const n of names) {
    if (!reachable.has(n)) {
      orphans.push(n);
      continue;
    }
    const r = rank.get(n) ?? 0;
    rows.set(r, [...(rows.get(r) || []), n]);
  }
  const widest = Math.max(1, ...Array.from(rows.values()).map((r) => r.length));
  const width = widest * (NODE_W + GAP_X) + (orphans.length ? NODE_W + GAP_X * 2 : 0) + GAP_X;
  const nodes: FlowNode[] = [];
  rows.forEach((row, r) => {
    const rowWidth = row.length * NODE_W + (row.length - 1) * GAP_X;
    const left = (widest * (NODE_W + GAP_X) - GAP_X - rowWidth) / 2 + GAP_X;
    row.forEach((n, i) => {
      const st = asObject(states[n]);
      nodes.push({
        name: n,
        type: str(st.type, "?"),
        x: left + i * (NODE_W + GAP_X),
        y: GAP_Y / 2 + r * (NODE_H + GAP_Y),
        terminal: st.end === true || st.type === "succeed" || st.type === "fail",
        unreachable: false,
      });
    });
  });
  orphans.forEach((n, i) => {
    const st = asObject(states[n]);
    nodes.push({
      name: n,
      type: str(st.type, "?"),
      x: widest * (NODE_W + GAP_X) + GAP_X,
      y: GAP_Y / 2 + i * (NODE_H + GAP_Y),
      terminal: st.end === true || st.type === "succeed" || st.type === "fail",
      unreachable: true,
    });
  });
  const maxRank = Math.max(0, ...Array.from(rows.keys()), orphans.length - 1);
  return { nodes, edges, width, height: (maxRank + 1) * (NODE_H + GAP_Y) + GAP_Y / 2 };
}

/** Rename a state and every reference to it (start_at, next, default, choices, catch). */
export function renameState(def: JsonObject, from: string, to: string): JsonObject {
  const states: JsonObject = {};
  for (const [name, raw] of Object.entries(asObject(def.states))) {
    const st = { ...asObject(raw) };
    if (st.next === from) st.next = to;
    if (st.default === from) st.default = to;
    if (Array.isArray(st.choices)) st.choices = st.choices.map((c) => (asObject(c).next === from ? { ...asObject(c), next: to } : c));
    if (Array.isArray(st.catch)) st.catch = st.catch.map((c) => (asObject(c).next === from ? { ...asObject(c), next: to } : c));
    states[name === from ? to : name] = st;
  }
  return { ...def, start_at: def.start_at === from ? to : def.start_at, states };
}

/** Delete a state; transitions into it are dropped (the source then ends). */
export function deleteState(def: JsonObject, name: string): JsonObject {
  const states: JsonObject = {};
  for (const [n, raw] of Object.entries(asObject(def.states))) {
    if (n === name) continue;
    const st = { ...asObject(raw) };
    if (st.next === name) {
      delete st.next;
      if (["task", "pass", "wait", "parallel", "map"].includes(str(st.type))) st.end = true;
    }
    if (st.default === name) delete st.default;
    if (Array.isArray(st.choices)) st.choices = st.choices.filter((c) => asObject(c).next !== name);
    if (Array.isArray(st.catch)) st.catch = st.catch.filter((c) => asObject(c).next !== name);
    states[n] = st;
  }
  const remaining = Object.keys(states);
  return { ...def, start_at: def.start_at === name ? remaining[0] || "" : def.start_at, states };
}

export function newState(type: string, functions: string[]): JsonObject {
  switch (type) {
    case "task":
      return { type, function: functions[0] || "", end: true };
    case "choice":
      return { type, choices: [{ variable: "$.status", equals: "ok", next: "" }] };
    case "wait":
      return { type, seconds: 10, end: true };
    case "parallel":
      return { type, branches: [{ start_at: "Branch1", states: { Branch1: { type: "pass", end: true } } }], end: true };
    case "map":
      return { type, items_path: "$.items", iterator: { start_at: "Item", states: { Item: { type: "pass", end: true } } }, end: true };
    case "fail":
      return { type, error: "Failed", cause: "" };
    default:
      return type === "pass" ? { type, end: true } : { type };
  }
}
