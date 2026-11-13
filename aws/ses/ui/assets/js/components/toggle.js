// A switch: toggle("Auto-refresh", { checked, onChange(checked) }) -> { el, box }

import { h } from "../core/dom.js";

export function toggle(label, { checked = false, onChange } = {}) {
  const box = h("input", { type: "checkbox", role: "switch", checked });
  box.addEventListener("change", () => onChange && onChange(box.checked));
  return { el: h("label", { class: "toggle" }, box, h("span", {}, label)), box };
}
