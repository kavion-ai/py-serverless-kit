// A segmented control: segmented([{ id: "kv", label: "Key/value" }, ...], { selected, onChange(id) })

import { h } from "../core/dom.js";

export function segmented(options, { selected, onChange, label = "View" } = {}) {
  let value = selected || options[0].id;
  const el = h("div", { class: "segmented", role: "group", "aria-label": label });
  const draw = () => el.replaceChildren(...options.map((o) => h("button", {
    type: "button",
    class: o.id === value ? "on" : "",
    "aria-pressed": o.id === value ? "true" : "false",
    onclick: () => {
      if (o.id === value) return;
      value = o.id;
      draw();
      if (onChange) onChange(value);
    },
  }, o.label)));
  draw();
  return {
    el,
    get value() {
      return value;
    },
    set(id) {
      value = id;
      draw();
    },
  };
}
