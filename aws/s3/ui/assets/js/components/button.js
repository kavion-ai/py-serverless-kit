// Buttons: normal, primary, link, icon-only, danger. A button with `href` is a link styled as a button.

import { h } from "../core/dom.js";
import { icon, spinner } from "./icons.js";

/**
 * button({label, variant: "normal"|"primary"|"link"|"inline"|"icon"|"danger", icon, iconRight, onClick, disabled,
 *         href, external, title, type})
 */
export function button(opts) {
  const { label, variant = "normal", onClick, disabled, href, external, title, type = "button", ariaLabel } = opts;
  const children = [
    opts.icon ? icon(opts.icon) : null,
    label ? h("span", { class: "btn__label" }, label) : null,
    opts.iconRight ? icon(opts.iconRight) : null,
  ];
  const cls = ["btn", `btn--${variant}`, opts.className];
  if (href) {
    return h(
      "a",
      {
        class: cls,
        href,
        title,
        "aria-label": ariaLabel,
        target: external ? "_blank" : undefined,
        rel: external ? "noopener noreferrer" : undefined,
        onclick: onClick,
      },
      children,
    );
  }
  return h(
    "button",
    { class: cls, type, disabled: Boolean(disabled), title, "aria-label": ariaLabel || (!label ? title : undefined), onclick: onClick },
    children,
  );
}

export function iconButton(name, title, onClick, opts = {}) {
  return button({ ...opts, variant: "icon", icon: name, title, ariaLabel: title, onClick });
}

/** A plain text link (AWS "link" style). */
export function link(label, href, opts = {}) {
  return h(
    "a",
    {
      class: ["link", opts.className],
      href,
      target: opts.external ? "_blank" : undefined,
      rel: opts.external ? "noopener noreferrer" : undefined,
      onclick: opts.onClick,
    },
    label,
    opts.external ? icon("external", { size: 12 }) : null,
  );
}

/** Shows a spinner on the button and disables it while `fn` runs. */
export async function busy(btn, fn) {
  const was = btn.disabled;
  btn.disabled = true;
  btn.classList.add("is-busy");
  const spin = spinner(14);
  btn.prepend(spin);
  try {
    return await fn();
  } finally {
    spin.remove();
    btn.classList.remove("is-busy");
    btn.disabled = was;
  }
}

/** A row of buttons. */
export function buttonRow(...buttons) {
  return h("div", { class: "btn-row" }, buttons);
}
