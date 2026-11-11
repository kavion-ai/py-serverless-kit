// Copy to clipboard (with a fallback for plain-HTTP origins where navigator.clipboard is unavailable).

import { h } from "../core/dom.js";
import { icon } from "./icons.js";
import { toast } from "./toast.js";

export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall back below */
  }
  const area = h("textarea", { readonly: true, style: { position: "fixed", left: "-9999px", top: "0" } });
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

/** Copy and confirm with a toast. `value` is a string or a function returning one. */
export async function copyWithToast(value, what = "Copied") {
  const text = typeof value === "function" ? value() : value;
  const ok = await copyText(text);
  toast(ok ? what : "Copy failed: select the text and copy it by hand");
  return ok;
}

/**
 * copyButton(value, {label, title, variant: "icon"|"normal"|"inline"}) - a small button that copies `value`.
 */
export function copyButton(value, opts = {}) {
  const { label, title = "Copy", variant = label ? "normal" : "icon" } = opts;
  const btn = h(
    "button",
    {
      type: "button",
      class: ["btn", `btn--${variant}`, "copy-btn"],
      title,
      "aria-label": label ? undefined : title,
      onclick: async (e) => {
        e.stopPropagation();
        const ok = await copyWithToast(value, opts.done || "Copied");
        if (ok) {
          btn.classList.add("is-copied");
          setTimeout(() => btn.classList.remove("is-copied"), 1500);
        }
      },
    },
    icon("copy", { size: 14 }),
    label ? h("span", { class: "btn__label" }, label) : null,
  );
  return btn;
}

/** Text followed by an inline copy icon. */
export function copyable(text, opts = {}) {
  return h("span", { class: ["copyable", opts.mono ? "mono" : ""] }, copyButton(text, { title: opts.title || "Copy" }), h("span", { class: "copyable__text" }, text));
}
