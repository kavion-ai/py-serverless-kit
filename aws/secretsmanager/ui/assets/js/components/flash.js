// Flashbar: notifications stacked at the top of the content area (success / error / info / warning).
//   flash.success("Secret stored", "prod/db was created.")
// Success and info messages close themselves after a few seconds; errors stay until dismissed.

import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";

let area = null;

/** The element the shell puts above each page. */
export function flashArea() {
  area = h("div", { class: "flash-area", role: "region", "aria-label": "Notifications" });
  return area;
}

export function clearFlash() {
  if (area) area.replaceChildren();
}

function show(type, title, detail, { timeout } = {}) {
  if (!area) return null;
  const close = () => item.remove();
  const item = h("div", { class: ["flash", type], role: type === "error" ? "alert" : "status" },
    icon(type === "warning" ? "warning" : type),
    h("div", { class: "f-body" },
      h("div", { class: "f-title" }, title),
      detail ? h("div", {}, detail) : null),
    h("button", { type: "button", class: "btn icon", "aria-label": "Dismiss notification", onclick: close }, icon("close")));
  area.prepend(item);
  while (area.children.length > 4) area.lastChild.remove();
  const ms = timeout === undefined ? (type === "error" || type === "warning" ? 0 : 6000) : timeout;
  if (ms) setTimeout(close, ms);
  return item;
}

export const flash = {
  success: (title, detail, opts) => show("success", title, detail, opts),
  info: (title, detail, opts) => show("info", title, detail, opts),
  warning: (title, detail, opts) => show("warning", title, detail, opts),
  /** An ApiError (or any Error) as an error notification. */
  error: (title, err, opts) => show("error", title, err ? (err.text || err.message || String(err)) : "", opts),
};
