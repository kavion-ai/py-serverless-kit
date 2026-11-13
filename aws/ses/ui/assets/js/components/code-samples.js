// Sample code with a language switcher and a copy button:
//   codeSamples([{ id: "python", label: "Python (smtplib)", code: "..." }, ...])

import { h } from "../core/dom.js";
import { copyButton } from "./copy-button.js";
import { segmented } from "./segmented.js";

export function codeSamples(samples) {
  let lang = samples[0].id;
  const pre = h("pre", { class: "code" });
  const draw = () => {
    pre.textContent = (samples.find((s) => s.id === lang) || samples[0]).code;
  };
  const tabs = segmented(samples.map((s) => ({ id: s.id, label: s.label })), {
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
