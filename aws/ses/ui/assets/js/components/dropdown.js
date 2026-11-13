// An "Actions" menu button: dropdown("Actions", [{ label, onSelect, disabled }]). Esc or a click outside closes it;
// arrow keys move through the items.

import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";

export function dropdown(label, items, { variant = "normal" } = {}) {
  const menu = h("div", { class: "menu", role: "menu", hidden: true });
  const trigger = h("button", {
    type: "button", class: ["btn", variant !== "normal" && variant], "aria-haspopup": "menu", "aria-expanded": "false",
  }, label, icon("caretDown"));
  const root = h("div", { class: "dropdown" }, trigger, menu);

  const outside = (e) => {
    if (!root.contains(e.target)) close();
  };
  function close() {
    menu.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    document.removeEventListener("mousedown", outside);
  }
  function open() {
    menu.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    document.addEventListener("mousedown", outside);
    const first = menu.querySelector("button:not(:disabled)");
    if (first) first.focus();
  }

  menu.replaceChildren(...items.filter(Boolean).map((item) => h("button", {
    type: "button",
    role: "menuitem",
    disabled: Boolean(item.disabled),
    onclick: () => {
      close();
      trigger.focus();
      item.onSelect();
    },
  }, item.label)));

  trigger.addEventListener("click", () => (menu.hidden ? open() : close()));
  root.addEventListener("keydown", (e) => {
    if (menu.hidden) return;
    if (e.key === "Escape") {
      e.stopPropagation();
      close();
      trigger.focus();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const buttons = [...menu.querySelectorAll("button:not(:disabled)")];
      const at = buttons.indexOf(document.activeElement);
      const next = e.key === "ArrowDown" ? (at + 1) % buttons.length : (at - 1 + buttons.length) % buttons.length;
      if (buttons[next]) buttons[next].focus();
    }
  });
  return root;
}
