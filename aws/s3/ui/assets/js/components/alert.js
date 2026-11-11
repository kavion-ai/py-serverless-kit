// In-page alerts (info, success, warning, error).

import { h } from "../core/dom.js";
import { icon } from "./icons.js";

/** alert({type, title, action, dismissible}, ...content) */
export function alert(opts, ...content) {
  const { type = "info", title, action, dismissible, onDismiss } = opts || {};
  const el = h(
    "div",
    { class: `alert alert--${type}`, role: type === "error" ? "alert" : "status" },
    h("span", { class: "alert__icon" }, icon(type === "success" ? "success" : type === "error" ? "error" : type === "warning" ? "warning" : "info", { size: 18 })),
    h("div", { class: "alert__body" }, title ? h("div", { class: "alert__title" }, title) : null, content.length ? h("div", { class: "alert__content" }, content) : null),
    action ? h("div", { class: "alert__action" }, action) : null,
    dismissible
      ? h(
          "button",
          {
            type: "button",
            class: "alert__dismiss",
            "aria-label": "Dismiss",
            onclick: () => {
              el.remove();
              if (onDismiss) onDismiss();
            },
          },
          icon("close", { size: 14 }),
        )
      : null,
  );
  return el;
}

/** A slot that shows one error alert at a time: slot.set(message|Error|null). */
export function errorSlot() {
  const el = h("div", { class: "error-slot" });
  el.set = (message, title = "Error") => {
    el.replaceChildren();
    if (message) {
      el.append(alert({ type: "error", title, dismissible: true }, message instanceof Error ? message.message : String(message)));
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  };
  return el;
}
