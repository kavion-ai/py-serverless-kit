// Small CSS-only charts (no chart library).
//   statTile({ label, value, detail, tone })                 a number with a caption
//   meter({ value, max, label })                             a usage bar (quota)
//   barChart(days, series)                                   grouped bars per day:
//     days = [{ Date, Sent, Delivered, ... }], series = [{ key: "Sent", label: "Sent", cls: "sent" }]

import { h } from "../core/dom.js";

export function statTile({ label, value, detail, tone } = {}) {
  return h("div", { class: ["stat", tone] },
    h("div", { class: "stat-label" }, label),
    h("div", { class: "stat-value" }, value),
    detail ? h("div", { class: "stat-detail" }, detail) : null);
}

export function meter({ value = 0, max = 0, label = "Usage" } = {}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const bar = h("div", { class: ["meter-fill", pct >= 90 ? "high" : pct >= 70 ? "mid" : ""] });
  bar.style.width = `${pct.toFixed(1)}%`;
  return h("div", {
    class: "meter", role: "meter", "aria-label": label, "aria-valuemin": "0", "aria-valuemax": String(max),
    "aria-valuenow": String(value),
  }, bar);
}

export function barChart(days, series, { formatDay } = {}) {
  const max = Math.max(1, ...days.flatMap((d) => series.map((s) => Number(d[s.key]) || 0)));
  const fmt = formatDay || ((ts) => {
    const d = new Date(ts * 1000);
    return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
  });
  const cols = days.map((d) => {
    const bars = series.map((s) => {
      const v = Number(d[s.key]) || 0;
      const bar = h("span", { class: ["bar", s.cls], title: `${s.label}: ${v}` });
      bar.style.height = `${v ? Math.max(2, (v / max) * 100) : 0}%`;
      return bar;
    });
    const total = series.map((s) => `${s.label} ${Number(d[s.key]) || 0}`).join(", ");
    return h("div", { class: "bar-col", role: "listitem", "aria-label": `${fmt(d.Date)}: ${total}` },
      h("div", { class: "bar-stack", "aria-hidden": "true" }, bars),
      h("div", { class: "bar-day", "aria-hidden": "true" }, fmt(d.Date)));
  });
  const legend = h("div", { class: "legend" }, series.map((s) => h("span", { class: "legend-item" },
    h("span", { class: ["swatch", s.cls], "aria-hidden": "true" }), s.label)));
  return h("div", { class: "chart" },
    h("div", { class: "chart-scale", "aria-hidden": "true" }, h("span", {}, String(max)), h("span", {}, "0")),
    h("div", { class: "bars", role: "list", "aria-label": "Recipients per day (UTC)" }, cols),
    legend);
}
