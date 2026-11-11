// A JSON editor: monospace textarea with a line-number gutter and live validation.
//
// jsonEditor({value, rows, validate(parsed) -> string|null, allowEmpty, onChange, ariaLabel})
// -> {el, getValue(), setValue(text), parsed() (throws when invalid), isValid(), focus()}

import { h } from "../core/dom.js";
import { icon } from "./icons.js";

/** Line and column of a JSON.parse error, from the message's "position N" or "(line L column C)". */
function errorLocation(message, text) {
  const lc = /line (\d+) column (\d+)/i.exec(message);
  if (lc) return { line: Number(lc[1]), column: Number(lc[2]) };
  const pos = /position (\d+)/i.exec(message);
  if (!pos) return null;
  const before = text.slice(0, Number(pos[1]));
  const lines = before.split("\n");
  return { line: lines.length, column: lines[lines.length - 1].length + 1 };
}

export function jsonEditor({ value = "", rows = 18, validate, allowEmpty = false, onChange, ariaLabel = "JSON" } = {}) {
  const gutter = h("div", { class: "json-editor__gutter", "aria-hidden": "true" });
  const area = h("textarea", { class: "json-editor__text", rows, spellcheck: "false", autocomplete: "off", "aria-label": ariaLabel, wrap: "off" });
  area.value = value;
  const status = h("div", { class: "json-editor__status", "aria-live": "polite" });
  const el = h("div", { class: "json-editor" }, h("div", { class: "json-editor__frame" }, gutter, area), status);
  let valid = true;
  let errorLine = 0;

  function drawGutter() {
    const count = area.value.split("\n").length;
    const nodes = [];
    for (let i = 1; i <= count; i += 1) nodes.push(h("div", { class: i === errorLine ? "is-error" : "" }, String(i)));
    gutter.replaceChildren(...nodes);
    gutter.scrollTop = area.scrollTop;
  }

  function check() {
    const text = area.value;
    errorLine = 0;
    let message = "";
    if (!text.trim()) {
      valid = allowEmpty;
      message = allowEmpty ? "" : "Enter a JSON document.";
    } else {
      try {
        const parsed = JSON.parse(text);
        const problem = validate ? validate(parsed) : null;
        valid = !problem;
        message = problem || "";
      } catch (e) {
        valid = false;
        const loc = errorLocation(e.message, text);
        if (loc) errorLine = loc.line;
        message = loc ? `Invalid JSON at line ${loc.line}, column ${loc.column}: ${e.message.replace(/ in JSON at position \d+.*$/, "")}` : `Invalid JSON: ${e.message}`;
      }
    }
    status.replaceChildren(
      message
        ? h("span", { class: "json-editor__error" }, icon("error", { size: 14 }), h("span", {}, message))
        : text.trim()
          ? h("span", { class: "json-editor__ok" }, icon("success", { size: 14 }), h("span", {}, "Valid JSON"))
          : "",
    );
    area.classList.toggle("is-invalid", !valid && Boolean(text.trim()));
    drawGutter();
    return valid;
  }

  area.addEventListener("input", () => {
    check();
    if (onChange) onChange(area.value);
  });
  area.addEventListener("scroll", () => {
    gutter.scrollTop = area.scrollTop;
  });
  area.addEventListener("keydown", (e) => {
    if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) {
      // Two spaces instead of leaving the field; Escape then Tab still moves focus.
      if (area.dataset.escaped === "1") {
        area.dataset.escaped = "";
        return;
      }
      e.preventDefault();
      const { selectionStart: s, selectionEnd: end } = area;
      area.setRangeText("  ", s, end, "end");
      check();
    } else if (e.key === "Escape") {
      area.dataset.escaped = "1";
    } else {
      area.dataset.escaped = "";
    }
  });
  check();

  return {
    el,
    getValue: () => area.value,
    setValue(text) {
      area.value = text;
      check();
      if (onChange) onChange(text);
    },
    parsed() {
      if (!check()) throw new Error("The JSON is not valid.");
      return area.value.trim() ? JSON.parse(area.value) : null;
    },
    isValid: () => check(),
    focus: () => area.focus(),
  };
}

export function prettyJson(text) {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}
