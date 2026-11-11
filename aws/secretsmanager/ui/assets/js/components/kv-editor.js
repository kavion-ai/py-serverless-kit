// The secret value editor: "Key/value" rows or "Plaintext", plus "Generate password".
//   const ed = kvEditor({ initial: '{"user":"app"}', generate: async () => "random" })
//   ed.el; ed.value() -> the SecretString (key/value rows become a JSON object); throws Error on bad rows
// Values sit in password inputs and show while focused, so they are not on screen by default.

import { h } from "../core/dom.js";
import { parseObject, stringify } from "../core/format.js";
import { button } from "./button.js";
import { segmented } from "./segmented.js";

export function kvEditor({ initial = "", generate, mode: startMode } = {}) {
  const obj = initial === "" ? {} : parseObject(initial);
  let mode = startMode || (obj ? "kv" : "text");
  const rows = h("div", { class: "kv-rows" });
  const text = h("textarea", { spellcheck: "false", rows: 8, "aria-label": "Plaintext secret value", autocomplete: "off" });
  text.value = obj ? JSON.stringify(obj, null, 2) : initial;
  const body = h("div");
  const error = h("div", { class: "f-error", role: "alert" });

  function addRow(key = "", value = "") {
    const k = h("input", { type: "text", placeholder: "key", "aria-label": "Secret key", value: key, autocomplete: "off", spellcheck: "false" });
    const v = h("input", {
      type: "password", placeholder: "value", "aria-label": `Value of ${key || "key"}`, value, autocomplete: "new-password", spellcheck: "false",
      onfocus: (e) => { e.target.type = "text"; },
      onblur: (e) => { e.target.type = "password"; },
    });
    const row = h("div", { class: "kv-row" }, k, v, button("Remove", { onClick: () => row.remove() }));
    rows.append(row);
    return row;
  }

  function rowsToJson() {
    const out = {};
    for (const row of rows.children) {
      const [k, v] = row.querySelectorAll("input");
      const key = k.value.trim();
      if (!key && !v.value) continue;
      if (!key) throw new Error("Every row needs a key.");
      if (Object.prototype.hasOwnProperty.call(out, key)) throw new Error(`The key "${key}" is used twice.`);
      out[key] = v.value;
    }
    return JSON.stringify(out);
  }

  function fillRows(source) {
    rows.replaceChildren();
    Object.entries(source || {}).forEach(([k, v]) => addRow(k, stringify(v)));
    if (!rows.children.length) addRow();
  }

  const switcher = segmented([{ id: "kv", label: "Key/value" }, { id: "text", label: "Plaintext" }], {
    selected: mode,
    label: "Value format",
    onChange: (next) => {
      error.textContent = "";
      if (next === "text") {
        try {
          text.value = JSON.stringify(JSON.parse(rowsToJson()), null, 2);
        } catch (err) {
          error.textContent = err.message;
          switcher.set("kv");
          return;
        }
      } else {
        const parsed = text.value.trim() ? parseObject(text.value) : {};
        if (!parsed) {
          error.textContent = "The plaintext is not a JSON object, so it can't be shown as key/value pairs.";
          switcher.set("text");
          return;
        }
        fillRows(parsed);
      }
      mode = next;
      draw();
    },
  });

  const genBtn = generate ? button("Generate password", {
    variant: "link",
    icon: "key",
    onClick: async () => {
      error.textContent = "";
      try {
        const pw = await generate();
        if (mode === "kv") {
          const empty = [...rows.children].find((r) => !r.querySelectorAll("input")[0].value && !r.querySelectorAll("input")[1].value);
          const row = empty || addRow();
          const [k, v] = row.querySelectorAll("input");
          if (!k.value) k.value = "password";
          v.value = pw;
        } else {
          text.value = pw;
        }
      } catch (err) {
        error.textContent = err.text || err.message;
      }
    },
  }) : null;

  function draw() {
    body.replaceChildren(mode === "kv"
      ? h("div", { class: "stack" },
        h("div", { class: "kv-head" }, h("span", {}, "Key"), h("span", {}, "Value"), h("span", {})),
        rows,
        h("div", { class: "row" }, button("Add row", { icon: "plus", onClick: () => addRow().querySelector("input").focus() })))
      : text);
  }

  fillRows(obj);
  draw();

  return {
    el: h("div", {}, h("div", { class: "editor-bar" }, switcher.el, h("span", { class: "grow" }), genBtn), body, error),
    value() {
      error.textContent = "";
      try {
        return mode === "kv" ? rowsToJson() : text.value;
      } catch (err) {
        error.textContent = err.message;
        throw err;
      }
    },
    get mode() {
      return mode;
    },
  };
}
