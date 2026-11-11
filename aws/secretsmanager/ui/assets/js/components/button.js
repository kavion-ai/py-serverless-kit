// Buttons. variant: "normal" (default), "primary", "link", "inline", "icon"; danger: true for destructive actions.
//   const b = button("Save", { variant: "primary", onClick: async () => {...} })
// When onClick returns a promise the button shows a spinner and is disabled until it settles.

import { h } from "../core/dom.js";
import { icon as svg } from "../core/icons.js";

export function button(label, { variant = "normal", danger = false, icon, onClick, type = "button", disabled = false,
  ariaLabel, title } = {}) {
  const cls = ["btn", variant !== "normal" && variant, danger && "danger"];
  const content = () => [icon ? svg(icon) : null, variant === "icon" ? null : label];
  const el = h("button", {
    type,
    class: cls,
    disabled,
    title: title || (variant === "icon" ? label : undefined),
    "aria-label": ariaLabel || (variant === "icon" ? label : undefined),
  }, content());
  if (onClick) {
    el.addEventListener("click", async (event) => {
      const result = onClick(event);
      if (result && typeof result.then === "function") {
        setLoading(el, true);
        try {
          await result;
        } catch {
          /* the caller reports its own errors */
        } finally {
          if (el.isConnected) setLoading(el, false, content());
        }
      }
    });
  }
  return el;
}

/** Spinner + disabled while busy; restores `content` (or the previous children) after. */
export function setLoading(el, busy, content) {
  if (busy) {
    el._saved = [...el.childNodes];
    el.disabled = true;
    el.setAttribute("aria-busy", "true");
    el.prepend(h("span", { class: "spinner", "aria-hidden": "true" }));
    const first = el.querySelector("svg");
    if (first) first.remove();
  } else {
    el.disabled = false;
    el.removeAttribute("aria-busy");
    el.replaceChildren(...(content || el._saved || []).filter(Boolean));
  }
}

export function buttonGroup(...buttons) {
  return h("div", { class: "btn-group" }, buttons);
}
