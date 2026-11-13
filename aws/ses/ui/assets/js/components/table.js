// A data table inside a container, like the AWS console's tables.
//
//   const t = table({
//     title: "Identities", actions: [buttons], description,
//     columns: [{ id, header, cell: (row) => node|string, sort: (row) => value }],
//     items, trackBy: (row) => key,
//     selection: "single" | null, onSelect: (row|null) => {},
//     filter: { placeholder, match: (row, text) => bool }          // client-side filter
//          | { placeholder, onInput: (text) => {}, value },        // server-side filter (debounced by the caller)
//     tools: [nodes next to the filter], pageSize: 20 (client paging), empty: node | () => node, footer: node,
//   });
//   t.setItems(rows); t.setLoading(true); t.selected();

import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { container } from "./container.js";

export function table(opts) {
  const { columns, selection = null, onSelect, filter, tools = [], pageSize = 0, empty, trackBy = (r, i) => i } = opts;
  let items = opts.items || [];
  let loading = Boolean(opts.loading);
  let sort = opts.sort || null; // { id, desc }
  let text = filter && filter.value ? filter.value : "";
  let page = 0;
  let selectedKey = null;
  const radioName = `sel-${Math.random().toString(36).slice(2)}`;

  const tbody = h("tbody");
  const thead = h("thead");
  const pager = h("div", { class: "pager" });
  const counter = h("span", { class: "counter" });

  const visible = () => {
    let rows = items;
    if (filter && filter.match && text.trim()) rows = rows.filter((r) => filter.match(r, text.trim().toLowerCase()));
    if (sort) {
      const col = columns.find((c) => c.id === sort.id);
      if (col && col.sort) {
        rows = [...rows].sort((a, b) => {
          const x = col.sort(a);
          const y = col.sort(b);
          const cmp = x < y ? -1 : x > y ? 1 : 0;
          return sort.desc ? -cmp : cmp;
        });
      }
    }
    return rows;
  };

  function drawHead() {
    const cells = columns.map((c) => {
      const active = sort && sort.id === c.id;
      const attrs = { scope: "col", style: c.width ? `width:${c.width}` : undefined };
      if (!c.sort) return h("th", attrs, c.header);
      return h("th", {
        ...attrs,
        class: "sortable",
        tabindex: "0",
        "aria-sort": active ? (sort.desc ? "descending" : "ascending") : "none",
        onclick: () => toggleSort(c.id),
        onkeydown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleSort(c.id);
          }
        },
      }, c.header, h("span", { class: "sort", "aria-hidden": "true" }, active ? (sort.desc ? "▼" : "▲") : "↕"));
    });
    thead.replaceChildren(h("tr", {}, selection ? h("th", { class: "sel" }, h("span", { class: "sr-only" }, "Select")) : null, cells));
  }

  function toggleSort(id) {
    sort = sort && sort.id === id ? { id, desc: !sort.desc } : { id, desc: false };
    drawHead();
    drawBody();
  }

  function drawBody() {
    const span = columns.length + (selection ? 1 : 0);
    const rows = visible();
    counter.textContent = loading ? "" : `(${rows.length}${filter && filter.match && text.trim() ? `/${items.length}` : ""})`;
    if (loading) {
      tbody.replaceChildren(h("tr", {}, h("td", { colspan: span },
        h("div", { class: "table-empty" }, h("span", { class: "spinner" }), " Loading…"))));
      pager.replaceChildren();
      return;
    }
    if (!rows.length) {
      const msg = items.length ? h("div", { class: "table-empty" }, h("b", {}, "No matches"), "Nothing matches the filter.") : ((typeof empty === "function" ? empty() : empty) || h("div", { class: "table-empty" }, h("b", {}, "No items")));
      tbody.replaceChildren(h("tr", {}, h("td", { colspan: span }, msg)));
      pager.replaceChildren();
      return;
    }
    const pages = pageSize ? Math.max(1, Math.ceil(rows.length / pageSize)) : 1;
    page = Math.min(page, pages - 1);
    const shown = pageSize ? rows.slice(page * pageSize, (page + 1) * pageSize) : rows;
    tbody.replaceChildren(...shown.map((row, i) => {
      const key = trackBy(row, i);
      const isSel = selection && key === selectedKey;
      const tr = h("tr", { class: isSel ? "selected" : "" },
        selection ? h("td", { class: "sel" }, h("input", {
          type: "radio", name: radioName, checked: isSel, "aria-label": "Select row",
          onchange: () => choose(row, key),
        })) : null,
        columns.map((c) => h("td", { class: c.wrap ? "cell-wrap" : undefined }, c.cell(row))));
      return tr;
    }));
    drawPager(pages);
  }

  function drawPager(pages) {
    if (!pageSize || pages <= 1) {
      pager.replaceChildren();
      return;
    }
    const go = (p) => {
      page = p;
      drawBody();
    };
    pager.replaceChildren(
      h("button", { type: "button", class: "btn icon", "aria-label": "Previous page", disabled: page === 0, onclick: () => go(page - 1) }, icon("caretLeft")),
      h("span", {}, `${page + 1} / ${pages}`),
      h("button", { type: "button", class: "btn icon", "aria-label": "Next page", disabled: page >= pages - 1, onclick: () => go(page + 1) }, icon("caretRight")));
  }

  function choose(row, key) {
    selectedKey = key;
    drawBody();
    if (onSelect) onSelect(row);
  }

  let filterEl = null;
  if (filter) {
    const box = h("input", { type: "search", placeholder: filter.placeholder || "Find", "aria-label": filter.placeholder || "Find", value: text });
    box.addEventListener("input", () => {
      text = box.value;
      page = 0;
      if (filter.onInput) filter.onInput(text);
      else drawBody();
    });
    filterEl = h("div", { class: "filter" }, icon("search"), box);
  }

  drawHead();
  drawBody();

  const toolbar = filterEl || tools.length || pageSize ? h("div", { class: "table-tools" }, filterEl, tools, h("span", { class: "grow" }), pager) : null;
  const el = container({
    title: opts.title ? h("span", {}, opts.title, " ", counter) : undefined,
    description: opts.description,
    actions: opts.actions || [],
    flush: true,
    footer: opts.footer,
  }, toolbar, h("div", { class: "table-wrap" }, h("table", { class: "tbl" }, thead, tbody)));

  return {
    el,
    setItems(rows) {
      items = rows || [];
      loading = false;
      if (selection && selectedKey !== null && !items.some((r, i) => trackBy(r, i) === selectedKey)) {
        selectedKey = null;
        if (onSelect) onSelect(null);
      }
      drawBody();
    },
    setLoading(on) {
      loading = on;
      drawBody();
    },
    selected() {
      return items.find((r, i) => trackBy(r, i) === selectedKey) || null;
    },
  };
}
