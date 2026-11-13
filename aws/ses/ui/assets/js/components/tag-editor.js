// Tag rows (Key / Value / Remove) with "Add new tag", like the AWS tag editor.
//   const tags = tagEditor([{ Key, Value }]); tags.el; tags.value() -> [{Key, Value}] or throws Error on bad input

import { h } from "../core/dom.js";
import { button } from "./button.js";

const MAX = 50;

export function tagEditor(initial = []) {
  const rows = h("div", { class: "kv-rows" });
  const head = h("div", { class: "kv-head" }, h("span", {}, "Key"), h("span", {}, "Value - optional"), h("span", {}));
  const note = h("div", { class: "f-constraint" });
  const add = button("Add new tag", { icon: "plus", onClick: () => addRow() });

  function addRow(key = "", value = "") {
    const k = h("input", { type: "text", placeholder: "Enter key", "aria-label": "Tag key", maxlength: "128", value: key, autocomplete: "off" });
    const v = h("input", { type: "text", placeholder: "Enter value", "aria-label": "Tag value", maxlength: "256", value, autocomplete: "off" });
    const row = h("div", { class: "kv-row" }, k, v, button("Remove", {
      onClick: () => {
        row.remove();
        refresh();
      },
    }));
    rows.append(row);
    refresh();
    if (!key) k.focus();
  }

  function refresh() {
    const n = rows.children.length;
    head.hidden = n === 0;
    add.disabled = n >= MAX;
    note.textContent = n ? `You can add ${MAX - n} more tags.` : "No tags associated with the resource.";
  }

  initial.forEach((t) => addRow(t.Key, t.Value));
  refresh();

  return {
    el: h("div", { class: "stack" }, head, rows, h("div", { class: "row" }, add), note),
    value() {
      const out = [];
      const seen = new Set();
      for (const row of rows.children) {
        const [k, v] = row.querySelectorAll("input");
        const key = k.value.trim();
        if (!key && !v.value.trim()) continue;
        if (!key) throw new Error("Every tag needs a key.");
        if (seen.has(key)) throw new Error(`The tag key "${key}" is used twice.`);
        seen.add(key);
        out.push({ Key: key, Value: v.value.trim() });
      }
      return out;
    },
  };
}
