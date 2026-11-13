// Inline alert: alert("warning", "Mail is kept, not sent", details, actionButton)
// type: info, success, warning or error.

import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";

export function alert(type, title, ...content) {
  return h("div", { class: ["alert", type], role: type === "error" ? "alert" : "status" },
    icon(type),
    h("div", { class: "a-body" },
      title ? h("div", { class: "a-title" }, title) : null,
      content.length ? h("div", {}, content) : null));
}
