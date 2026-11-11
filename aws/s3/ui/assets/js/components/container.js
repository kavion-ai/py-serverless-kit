// Containers (the white cards of the AWS console), expandable sections, loading and empty states.

import { h } from "../core/dom.js";
import { icon, spinner } from "./icons.js";

/** container({title, counter, description, actions, footer, variant}, ...children) */
export function container(opts, ...children) {
  const { title, counter, description, actions, footer, headingLevel = 2, id } = opts || {};
  const heading = h(`h${headingLevel}`, { class: "container__title" }, title, counter !== undefined && counter !== null ? h("span", { class: "counter" }, ` (${counter})`) : null);
  return h(
    "section",
    { class: ["container", opts && opts.variant ? `container--${opts.variant}` : ""], id },
    title || actions
      ? h(
          "div",
          { class: "container__header" },
          h("div", { class: "container__heading" }, title ? heading : null, description ? h("p", { class: "container__desc" }, description) : null),
          actions && actions.length ? h("div", { class: "container__actions" }, actions) : null,
        )
      : null,
    h("div", { class: "container__body" }, children),
    footer ? h("div", { class: "container__footer" }, footer) : null,
  );
}

/** An expandable section (<details>). */
export function expandable({ title, description, open }, ...children) {
  return h(
    "details",
    { class: "expandable", open: Boolean(open) },
    h("summary", {}, icon("caret-right", { size: 14, className: "expandable__caret" }), h("span", { class: "expandable__title" }, title)),
    description ? h("p", { class: "expandable__desc" }, description) : null,
    h("div", { class: "expandable__body" }, children),
  );
}

export function loading(text = "Loading") {
  return h("div", { class: "loading", role: "status" }, spinner(18), h("span", {}, text));
}

/** emptyState({title, text, action}) */
export function emptyState({ title, text, action }) {
  return h(
    "div",
    { class: "empty" },
    title ? h("div", { class: "empty__title" }, title) : null,
    text ? h("div", { class: "empty__text" }, text) : null,
    action ? h("div", { class: "empty__action" }, action) : null,
  );
}

/** The bottom bar of a form page: Cancel + primary action, right aligned. */
export function formActions(...buttons) {
  return h("div", { class: "form-actions" }, buttons);
}
