// A small icon button that copies `text` (a string or a function returning one) and says "Copied".

import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Insecure origins (plain http on a LAN address) have no clipboard API: use a hidden textarea.
    const area = h("textarea", { style: "position:fixed;opacity:0;left:-9999px", "aria-hidden": "true" });
    area.value = text;
    document.body.append(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }
}

export function copyButton(text, { label = "Copy", withText = false } = {}) {
  const idle = () => [icon("copy"), withText ? "Copy" : null].filter(Boolean);
  const el = h("button", { type: "button", class: withText ? "btn" : "btn icon", "aria-label": label, title: label }, idle());
  el.addEventListener("click", async () => {
    const ok = await copyText(typeof text === "function" ? text() : text);
    el.replaceChildren(...[icon(ok ? "check" : "error"), withText ? (ok ? "Copied" : "Copy failed") : null].filter(Boolean));
    el.title = ok ? "Copied" : "Copy failed: select and copy by hand";
    setTimeout(() => {
      el.replaceChildren(...idle());
      el.title = label;
    }, 1500);
  });
  return el;
}
