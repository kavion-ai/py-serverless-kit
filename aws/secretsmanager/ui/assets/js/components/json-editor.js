// A JSON text editor with line numbers and a live "valid / not valid" message.
//   const ed = jsonEditor({ value, placeholder, allowEmpty: true })
//   ed.el, ed.value(), ed.valid(), ed.set(text), ed.format()

import { h } from "../core/dom.js";

export function jsonEditor({ value = "", placeholder = "", allowEmpty = true, label = "JSON", rows = 12 } = {}) {
  const gutter = h("div", { class: "gutter", "aria-hidden": "true" });
  const area = h("textarea", { spellcheck: "false", placeholder, rows, "aria-label": label, wrap: "off" });
  area.value = value;
  const status = h("div", { class: "json-status", "aria-live": "polite" });

  const check = () => {
    const text = area.value;
    gutter.textContent = Array.from({ length: Math.max(1, text.split("\n").length) }, (_, i) => i + 1).join("\n");
    gutter.scrollTop = area.scrollTop;
    if (!text.trim()) {
      status.className = "json-status";
      status.textContent = allowEmpty ? "" : "Enter a JSON document.";
      return allowEmpty;
    }
    try {
      JSON.parse(text);
      status.className = "json-status ok";
      status.textContent = "Valid JSON";
      return true;
    } catch (err) {
      status.className = "json-status bad";
      status.textContent = `Not valid JSON: ${err.message}`;
      return false;
    }
  };
  area.addEventListener("input", check);
  area.addEventListener("scroll", () => {
    gutter.scrollTop = area.scrollTop;
  });
  area.addEventListener("keydown", (e) => {
    if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.altKey) {
      // Two spaces instead of leaving the field; Esc then Tab still moves focus on.
      if (area.dataset.escaped === "1") return;
      e.preventDefault();
      const { selectionStart: s, selectionEnd: t } = area;
      area.setRangeText("  ", s, t, "end");
      check();
    }
    area.dataset.escaped = e.key === "Escape" ? "1" : "";
  });
  check();

  return {
    el: h("div", {}, h("div", { class: "json-editor" }, gutter, area), status),
    value: () => area.value,
    valid: check,
    set(text) {
      area.value = text;
      check();
    },
    format() {
      try {
        area.value = JSON.stringify(JSON.parse(area.value), null, 2);
      } catch {
        /* leave it: the status already says why */
      }
      check();
    },
    focus: () => area.focus(),
  };
}
