// Flash banners at the top of the page (like the AWS console's flashbar) and small transient toasts.

import { h } from "../core/dom.js";
import { icon } from "./icons.js";

let bar = null;
let toastEl = null;
const items = [];

/** Attach the flashbar to its slot in the page layout. */
export function attachFlashbar(el) {
  bar = el;
  draw();
}

function draw() {
  if (!bar) return;
  bar.replaceChildren(
    ...items.map((item) =>
      h(
        "div",
        { class: `flash flash--${item.type}`, role: item.type === "error" ? "alert" : "status" },
        icon(item.type === "success" ? "success" : item.type === "error" ? "error" : item.type === "warning" ? "warning" : "info", { size: 18 }),
        h("div", { class: "flash__body" }, item.title ? h("div", { class: "flash__title" }, item.title) : null, item.content),
        h("button", { type: "button", class: "flash__dismiss", "aria-label": "Dismiss", onclick: () => dismiss(item) }, icon("close", { size: 14 })),
      ),
    ),
  );
}

function dismiss(item) {
  const i = items.indexOf(item);
  if (i >= 0) items.splice(i, 1);
  draw();
}

/**
 * flash("success"|"error"|"info"|"warning", content, {title}) - shown at the top of the current page and kept for the
 * next page (a flash set just before navigating appears on the page navigated to).
 */
export function flash(type, content, opts = {}) {
  const item = { type, content, title: opts.title, pages: 0 };
  items.unshift(item);
  while (items.length > 4) items.pop();
  draw();
  if (type === "success" || type === "info") setTimeout(() => dismiss(item), opts.timeout || 12000);
  return item;
}

/** Called on every navigation: a flash survives one page change. */
export function ageFlashes() {
  for (const item of [...items]) {
    item.pages += 1;
    if (item.pages > 1) dismiss(item);
  }
}

export function clearFlashes() {
  items.length = 0;
  draw();
}

/** A short confirmation at the bottom of the screen ("Copied"). */
export function toast(text) {
  if (!toastEl) {
    toastEl = h("div", { class: "toast", role: "status", "aria-live": "polite" });
    document.body.append(toastEl);
  }
  toastEl.textContent = text;
  toastEl.classList.add("is-visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => toastEl.classList.remove("is-visible"), 2000);
}
