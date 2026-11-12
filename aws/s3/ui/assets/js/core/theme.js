// Light / dark / automatic theme, as in the Secrets Manager console. "auto" follows the OS (prefers-color-scheme);
// the choice is a per-viewer preference kept in localStorage.

const KEY = "s3console.theme";
const ORDER = ["auto", "light", "dark"];

export function currentTheme() {
  let t = "auto";
  try {
    t = window.localStorage.getItem(KEY) || "auto";
  } catch {
    /* storage can be unavailable (private windows) */
  }
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
  try {
    window.localStorage.setItem(KEY, next);
  } catch {
    /* the choice just isn't remembered */
  }
  applyTheme(next);
  return next;
}

export const THEME_LABEL = { auto: "Theme: automatic", light: "Theme: light", dark: "Theme: dark" };
export const THEME_ICON = { auto: "auto", light: "sun", dark: "moon" };
