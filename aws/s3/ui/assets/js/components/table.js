// A data table with optional single (radio) or multi (checkbox) selection, sorting, filtering and pagination.
//
// table({columns: [{id, header, cell(row), sortValue(row), width, align, className}], rows, rowKey(row),
//        selectable: null|"single"|"multi", isSelectable(row), onSelect(rows), pageSize, empty, noMatch,
//        filter: {placeholder, match(row, text), value}, loading, rowClass(row), ariaLabel, sort: {id, desc}})
// -> {el, setRows(rows, {keepSelection, keepPage}), setLoading(bool), selected(), clearSelection(), setFilter(text)}

import { h } from "../core/dom.js";
import { icon } from "./icons.js";
import { loading as loadingBlock, emptyState } from "./container.js";

const INTERACTIVE = "a, button, input, select, textarea, label, summary";

export function table(opts) {
  const { columns, selectable = null, onSelect, pageSize = 50, filter, ariaLabel = "Table" } = opts;
  const rowKey = opts.rowKey || ((row) => row.id);
  const isSelectable = opts.isSelectable || (() => true);
  let rows = opts.rows || [];
  let isLoading = Boolean(opts.loading);
  let page = 0;
  let sort = opts.sort ? { ...opts.sort } : null;
  let query = filter && filter.value ? filter.value : "";
  const selected = new Map();
  const groupName = `tbl-${Math.random().toString(36).slice(2)}`;

  const head = h("thead");
  const body = h("tbody");
  const tableEl = h("table", { class: "tbl", "aria-label": ariaLabel }, head, body);
  const status = h("div", { class: "tbl__status" });
  const pager = h("nav", { class: "pager", "aria-label": "Pagination" });
  const countEl = h("span", { class: "tbl__count" });
  const filterInput = filter
    ? h("input", {
        class: "input tbl__filter-input",
        type: "search",
        placeholder: filter.placeholder || "Find",
        "aria-label": filter.placeholder || "Find",
        value: query,
        oninput: (e) => {
          query = e.target.value;
          page = 0;
          render();
        },
      })
    : null;
  const toolbar = filter || pageSize
    ? h(
        "div",
        { class: "tbl__toolbar" },
        filterInput ? h("div", { class: "tbl__filter" }, icon("search", { size: 14, className: "tbl__filter-icon" }), filterInput) : h("div"),
        countEl,
        pager,
      )
    : null;
  const el = h("div", { class: "tbl-wrap" }, toolbar, h("div", { class: "tbl__scroll" }, tableEl), status);

  function visibleRows() {
    let list = rows;
    if (filter && query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter((row) => filter.match(row, q));
    }
    if (sort) {
      const col = columns.find((c) => c.id === sort.id);
      if (col && col.sortValue) {
        const dir = sort.desc ? -1 : 1;
        list = [...list].sort((a, b) => {
          const x = col.sortValue(a);
          const y = col.sortValue(b);
          if (x === y) return 0;
          if (x === undefined || x === null) return 1;
          if (y === undefined || y === null) return -1;
          return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * dir;
        });
      }
    }
    return list;
  }

  function emit() {
    if (onSelect) onSelect([...selected.values()]);
  }

  function toggleRow(row, on) {
    const key = rowKey(row);
    if (selectable === "single") {
      selected.clear();
      if (on) selected.set(key, row);
    } else if (on) selected.set(key, row);
    else selected.delete(key);
    render();
    emit();
  }

  function renderHead(pageRows) {
    const cells = [];
    if (selectable === "multi") {
      const candidates = pageRows.filter(isSelectable);
      const all = candidates.length > 0 && candidates.every((r) => selected.has(rowKey(r)));
      const some = candidates.some((r) => selected.has(rowKey(r)));
      cells.push(
        h(
          "th",
          { class: "tbl__select" },
          h("input", {
            type: "checkbox",
            "aria-label": "Select all on this page",
            checked: all,
            indeterminate: some && !all,
            disabled: !candidates.length,
            onchange: (e) => {
              for (const r of candidates) {
                if (e.target.checked) selected.set(rowKey(r), r);
                else selected.delete(rowKey(r));
              }
              render();
              emit();
            },
          }),
        ),
      );
    } else if (selectable === "single") {
      cells.push(h("th", { class: "tbl__select" }, h("span", { class: "sr-only" }, "Select")));
    }
    for (const col of columns) {
      const sorted = sort && sort.id === col.id;
      const label = col.sortValue
        ? h(
            "button",
            {
              type: "button",
              class: ["tbl__sort", sorted ? "is-sorted" : ""],
              onclick: () => {
                sort = sorted ? { id: col.id, desc: !sort.desc } : { id: col.id, desc: false };
                render();
              },
            },
            col.header,
            icon(sorted && sort.desc ? "caret-down" : "caret-down", { size: 12, className: sorted ? (sort.desc ? "sort-desc" : "sort-asc") : "sort-none" }),
          )
        : col.header;
      cells.push(
        h(
          "th",
          {
            class: [col.align ? `is-${col.align}` : "", col.className],
            style: col.width ? { width: col.width } : undefined,
            "aria-sort": sorted ? (sort.desc ? "descending" : "ascending") : undefined,
          },
          label,
        ),
      );
    }
    head.replaceChildren(h("tr", {}, cells));
  }

  function renderBody(pageRows) {
    body.replaceChildren(
      ...pageRows.map((row) => {
        const key = rowKey(row);
        const can = isSelectable(row);
        const isSel = selected.has(key);
        const cells = [];
        if (selectable) {
          cells.push(
            h(
              "td",
              { class: "tbl__select" },
              can
                ? h("input", {
                    type: selectable === "single" ? "radio" : "checkbox",
                    name: selectable === "single" ? groupName : undefined,
                    checked: isSel,
                    "aria-label": "Select row",
                    onchange: (e) => toggleRow(row, e.target.checked),
                  })
                : null,
            ),
          );
        }
        for (const col of columns) {
          cells.push(h("td", { class: [col.align ? `is-${col.align}` : "", col.className] }, col.cell(row)));
        }
        const tr = h("tr", { class: [isSel ? "is-selected" : "", opts.rowClass ? opts.rowClass(row) : ""] }, cells);
        if (selectable && can) {
          tr.addEventListener("click", (e) => {
            if (e.target.closest(INTERACTIVE)) return;
            toggleRow(row, selectable === "single" ? true : !selected.has(key));
          });
        }
        return tr;
      }),
    );
  }

  function renderPager(total) {
    if (!pageSize) return;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    if (page >= pages) page = pages - 1;
    const btn = (label, target, disabled, current, aria) =>
      h(
        "button",
        {
          type: "button",
          class: ["pager__btn", current ? "is-current" : ""],
          disabled: Boolean(disabled),
          "aria-current": current ? "page" : undefined,
          "aria-label": aria,
          onclick: () => {
            page = target;
            render();
          },
        },
        label,
      );
    const items = [btn(icon("caret-left", { size: 14 }), page - 1, page === 0, false, "Previous page")];
    const shown = new Set([0, pages - 1, page - 1, page, page + 1]);
    let gap = false;
    for (let i = 0; i < pages; i += 1) {
      if (shown.has(i)) {
        items.push(btn(String(i + 1), i, false, i === page, `Page ${i + 1}`));
        gap = false;
      } else if (!gap) {
        items.push(h("span", { class: "pager__gap" }, "…"));
        gap = true;
      }
    }
    items.push(btn(icon("caret-right", { size: 14 }), page + 1, page >= pages - 1, false, "Next page"));
    pager.replaceChildren(...items);
  }

  function render() {
    const list = visibleRows();
    const start = pageSize ? page * pageSize : 0;
    if (pageSize && start >= list.length && page > 0) page = Math.max(0, Math.ceil(list.length / pageSize) - 1);
    const pageRows = pageSize ? list.slice(page * pageSize, page * pageSize + pageSize) : list;
    renderHead(pageRows);
    renderBody(pageRows);
    renderPager(list.length);
    countEl.textContent = filter && query.trim() && !isLoading ? `${list.length} ${list.length === 1 ? "match" : "matches"}` : "";
    if (isLoading) status.replaceChildren(loadingBlock("Loading"));
    else if (!rows.length) status.replaceChildren(typeof opts.empty === "function" ? opts.empty() : opts.empty || emptyState({ title: "No items" }));
    else if (!list.length) status.replaceChildren(opts.noMatch || emptyState({ title: "No matches", text: "No items match the filter." }));
    else status.replaceChildren();
    status.hidden = !status.childNodes.length;
  }

  render();

  return {
    el,
    setRows(next, { keepSelection = false, keepPage = false } = {}) {
      rows = next || [];
      isLoading = false;
      if (!keepPage) page = 0;
      const keys = new Set(rows.map(rowKey));
      if (keepSelection) {
        for (const k of [...selected.keys()]) if (!keys.has(k)) selected.delete(k);
        for (const r of rows) if (selected.has(rowKey(r))) selected.set(rowKey(r), r);
      } else selected.clear();
      render();
      emit();
    },
    setLoading(value) {
      isLoading = value;
      if (value) {
        rows = [];
        selected.clear();
        emit();
      }
      render();
    },
    rows: () => rows,
    selected: () => [...selected.values()],
    clearSelection() {
      selected.clear();
      render();
      emit();
    },
    setFilter(text) {
      query = text;
      if (filterInput) filterInput.value = text;
      page = 0;
      render();
    },
  };
}
