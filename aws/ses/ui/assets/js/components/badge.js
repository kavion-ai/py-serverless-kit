// Status indicator with an icon: badge("success", "Enabled"); type is success, error, warning, info, pending or stopped.
// chip(text, { accent }) is a small label (tags, event types).

import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";

export function badge(type, text) {
  return h("span", { class: ["badge", type] }, icon(type), text);
}

export function chip(text, { accent = false } = {}) {
  return h("span", { class: ["chip", accent && "accent"] }, text);
}
