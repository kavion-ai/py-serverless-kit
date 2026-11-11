// A switch (e.g. "Show versions").

import { h } from "../core/dom.js";

export function toggle({ label, checked, onChange, disabled }) {
  const box = h("input", {
    type: "checkbox",
    role: "switch",
    checked: Boolean(checked),
    disabled: Boolean(disabled),
    onchange: (e) => onChange && onChange(e.target.checked),
  });
  const el = h("label", { class: ["toggle", disabled ? "is-disabled" : ""] }, box, h("span", { class: "toggle__track", "aria-hidden": "true" }, h("span", { class: "toggle__thumb" })), h("span", { class: "toggle__label" }, label));
  el.input = box;
  return el;
}
