// Light / dark / automatic theme. "auto" follows the OS (prefers-color-scheme); the choice is a per-viewer preference.

import { prefs } from "./state.js";

const ORDER = ["auto", "light", "dark"];

export function currentTheme() {
  const t = prefs.get("theme", "auto");
  return ORDER.includes(t) ? t : "auto";
}

export function applyTheme(theme = currentTheme()) {
  const root = document.documentElement;
  if (theme === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

/** Switch to the next theme and return it. */
export function cycleTheme() {
  const next = ORDER[(ORDER.indexOf(currentTheme()) + 1) % ORDER.length];
  prefs.set("theme", next);
  applyTheme(next);
  return next;
}

export const THEME_LABEL = { auto: "Theme: automatic", light: "Theme: light", dark: "Theme: dark" };
export const THEME_ICON = { auto: "auto", light: "sun", dark: "moon" };
