// Tabs: tabs({tabs: [{id, label}], active, onChange}). Left/Right arrow keys move between tabs.

import { h } from "../core/dom.js";

export function tabs({ tabs: list, active, onChange, ariaLabel = "Tabs" }) {
  const buttons = list.map((t) =>
    h(
      "button",
      {
        type: "button",
        role: "tab",
        class: ["tabs__tab", t.id === active ? "is-active" : ""],
        "aria-selected": t.id === active ? "true" : "false",
        tabindex: t.id === active ? "0" : "-1",
        onclick: () => {
          if (t.id !== active) onChange(t.id);
        },
      },
      t.label,
    ),
  );
  const el = h("div", { class: "tabs", role: "tablist", "aria-label": ariaLabel }, buttons);
  el.addEventListener("keydown", (e) => {
    const i = buttons.indexOf(document.activeElement);
    if (i < 0 || (e.key !== "ArrowRight" && e.key !== "ArrowLeft")) return;
    const next = buttons[(i + (e.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length];
    next.focus();
    next.click();
  });
  return el;
}
