// Dropdown menu button: dropdown({label, items: () => [{label, onClick, disabled, description} | {divider: true}
// | {header}], variant, align}). Items are computed each time the menu opens, so they follow the current selection.

import { h } from "../core/dom.js";
import { icon } from "./icons.js";

let openMenu = null;

function closeOpen() {
  if (openMenu) openMenu();
}

document.addEventListener("click", (e) => {
  if (openMenu && !e.target.closest(".dropdown.is-open")) closeOpen();
});

export function dropdown({ label, items, variant = "normal", align = "right", disabled, icon: iconName }) {
  const menu = h("ul", { class: ["dropdown__menu", `dropdown__menu--${align}`], role: "menu", hidden: true });
  const trigger = h(
    "button",
    { type: "button", class: ["btn", `btn--${variant}`, "dropdown__trigger"], "aria-haspopup": "menu", "aria-expanded": "false", disabled: Boolean(disabled) },
    iconName ? icon(iconName) : null,
    label ? h("span", { class: "btn__label" }, label) : null,
    icon("caret-down", { size: 14 }),
  );
  const el = h("div", { class: "dropdown" }, trigger, menu);

  const close = () => {
    menu.hidden = true;
    el.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    if (openMenu === close) openMenu = null;
  };

  const focusables = () => Array.from(menu.querySelectorAll("button:not([disabled])"));

  const open = () => {
    closeOpen();
    const list = typeof items === "function" ? items() : items;
    menu.replaceChildren(
      ...list.filter(Boolean).map((item) => {
        if (item.divider) return h("li", { class: "dropdown__divider", role: "separator" });
        if (item.header) return h("li", { class: "dropdown__header", role: "presentation" }, item.header);
        return h(
          "li",
          { role: "none" },
          h(
            "button",
            {
              type: "button",
              role: "menuitem",
              class: "dropdown__item",
              disabled: Boolean(item.disabled),
              title: item.disabled && item.disabledReason ? item.disabledReason : undefined,
              onclick: (e) => {
                e.stopPropagation();
                close();
                trigger.focus();
                item.onClick();
              },
            },
            h("span", {}, item.label),
            item.description ? h("span", { class: "dropdown__desc" }, item.description) : null,
          ),
        );
      }),
    );
    menu.hidden = false;
    el.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    openMenu = close;
    const first = focusables()[0];
    if (first) first.focus();
  };

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    if (menu.hidden) open();
    else close();
  });
  el.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !menu.hidden) {
      e.stopPropagation();
      close();
      trigger.focus();
    } else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !menu.hidden) {
      e.preventDefault();
      const list = focusables();
      const i = list.indexOf(document.activeElement);
      const next = list[(i + (e.key === "ArrowDown" ? 1 : list.length - 1)) % list.length];
      if (next) next.focus();
    } else if (e.key === "ArrowDown" && menu.hidden && document.activeElement === trigger) {
      e.preventDefault();
      open();
    }
  });
  el.setDisabled = (value) => {
    trigger.disabled = Boolean(value);
  };
  return el;
}
