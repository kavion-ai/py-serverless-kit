// Status indicators ("Enabled", "Public", "Succeeded"...).

import { h } from "../core/dom.js";
import { icon, spinner } from "./icons.js";

const ICONS = { success: "success", error: "error", warning: "warning", info: "info", stopped: "stopped" };

/** badge("success"|"error"|"warning"|"info"|"stopped"|"pending"|"neutral", text) */
export function badge(type, text) {
  const mark = type === "pending" ? spinner(14) : ICONS[type] ? icon(ICONS[type], { size: 14 }) : null;
  return h("span", { class: `status status--${type}` }, mark, h("span", {}, text));
}

/** A small pill label (e.g. "Current version"). */
export function pill(text, tone = "neutral") {
  return h("span", { class: `pill pill--${tone}` }, text);
}
