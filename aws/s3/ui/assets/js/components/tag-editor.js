// Key / value rows with Add and Remove (tags, user-defined metadata).
//
// tagEditor({tags, max, keyLabel, valueLabel, addLabel, keyMax, valueMax, emptyText})
// -> {el, getValue() -> {key: value}, validate() -> error text or ""}

import { h } from "../core/dom.js";
import { button } from "./button.js";

export function tagEditor({ tags = {}, max = 50, keyLabel = "Key", valueLabel = "Value - optional", addLabel = "Add tag", keyMax = 128, valueMax = 256, emptyText = "No tags associated with the resource." } = {}) {
  const list = h("div", { class: "tag-editor__rows" });
  const empty = h("div", { class: "tag-editor__empty" }, emptyText);
  const error = h("div", { class: "field__error", hidden: true });
  const counter = h("div", { class: "field__constraint" });
  let addBtn;

  function rowsEls() {
    return Array.from(list.children);
  }

  function refresh() {
    const n = rowsEls().length;
    empty.hidden = n > 0;
    addBtn.disabled = n >= max;
    counter.textContent = `You can add ${Math.max(0, max - n)} more ${max - n === 1 ? "tag" : "tags"}.`;
  }

  function addRow(k = "", v = "") {
    const key = h("input", { class: "input", value: k, maxlength: keyMax, "aria-label": keyLabel, placeholder: "Enter key", autocomplete: "off" });
    const value = h("input", { class: "input", value: v, maxlength: valueMax, "aria-label": valueLabel, placeholder: "Enter value", autocomplete: "off" });
    const row = h(
      "div",
      { class: "tag-editor__row" },
      h("div", { class: "tag-editor__cell" }, key),
      h("div", { class: "tag-editor__cell" }, value),
      button({
        label: "Remove",
        onClick: () => {
          row.remove();
          refresh();
        },
      }),
    );
    row.key = key;
    row.value = value;
    list.append(row);
    refresh();
    return row;
  }

  addBtn = button({ label: addLabel, onClick: () => addRow().key.focus() });
  const head = h("div", { class: "tag-editor__head" }, h("div", {}, keyLabel), h("div", {}, valueLabel), h("div"));
  const el = h("div", { class: "tag-editor" }, head, list, empty, error, h("div", { class: "tag-editor__foot" }, addBtn, counter));
  Object.entries(tags).forEach(([k, v]) => addRow(k, v));
  refresh();

  function validate() {
    const seen = new Set();
    for (const row of rowsEls()) {
      const k = row.key.value.trim();
      if (!k) return `Enter a ${keyLabel.toLowerCase()} for every row, or remove the empty rows.`;
      if (seen.has(k)) return `The ${keyLabel.toLowerCase()} "${k}" is used twice.`;
      seen.add(k);
    }
    return "";
  }

  return {
    el,
    validate() {
      const text = validate();
      error.hidden = !text;
      error.textContent = text;
      return text;
    },
    getValue() {
      const out = {};
      for (const row of rowsEls()) {
        const k = row.key.value.trim();
        if (k) out[k] = row.value.value;
      }
      return out;
    },
  };
}
