// Sample code with a language switcher and a copy button: codeSamples("prod/db")

import { h } from "../core/dom.js";
import { LANGUAGES, snippet } from "../core/snippets.js";
import { copyButton } from "./copy-button.js";
import { segmented } from "./segmented.js";

export function codeSamples(name, { languages = LANGUAGES } = {}) {
  let lang = languages[0].id;
  const pre = h("pre", { class: "code" });
  const draw = () => {
    pre.textContent = snippet(lang, name);
  };
  const tabs = segmented(languages.map((l) => ({ id: l.id, label: l.label })), {
    selected: lang,
    label: "Language",
    onChange: (id) => {
      lang = id;
      draw();
    },
  });
  draw();
  return h("div", { class: "stack" },
    h("div", { style: "overflow-x:auto" }, tabs.el),
    h("div", { class: "code-box" }, pre, copyButton(() => pre.textContent, { label: "Copy code" })));
}
