// Tabs: tabs([{ id, label, render: () => node }], { selected, onChange(id) }) -> element
// The panel is rendered each time its tab is chosen. Arrow keys move between tabs.

import { h } from "../core/dom.js";

export function tabs(items, { selected, onChange } = {}) {
  let current = items.some((t) => t.id === selected) ? selected : items[0].id;
  const list = h("div", { class: "tabs", role: "tablist" });
  const panel = h("div", { class: "tab-panel", role: "tabpanel" });

  const choose = (id, focus = false) => {
    current = id;
    draw();
    if (focus) list.querySelector(".on").focus();
    if (onChange) onChange(id);
  };

  function draw() {
    list.replaceChildren(...items.map((t) => h("button", {
      type: "button",
      role: "tab",
      id: `tab-${t.id}`,
      class: t.id === current ? "on" : "",
      "aria-selected": t.id === current ? "true" : "false",
      tabindex: t.id === current ? "0" : "-1",
      onclick: () => choose(t.id),
      onkeydown: (e) => {
        const at = items.findIndex((x) => x.id === current);
        if (e.key === "ArrowRight") choose(items[(at + 1) % items.length].id, true);
        if (e.key === "ArrowLeft") choose(items[(at - 1 + items.length) % items.length].id, true);
      },
    }, t.label)));
    panel.setAttribute("aria-labelledby", `tab-${current}`);
    panel.replaceChildren(items.find((t) => t.id === current).render());
  }

  draw();
  return h("div", { class: "tabs-wrap" }, list, panel);
}
