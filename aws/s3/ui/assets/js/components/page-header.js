// The page header: title (+ optional info text, counter), description and action buttons on the right.

import { h } from "../core/dom.js";

/** pageHeader({title, counter, description, actions: [nodes], extra}) */
export function pageHeader({ title, counter, description, actions, extra }) {
  return h(
    "header",
    { class: "page-header" },
    h(
      "div",
      { class: "page-header__main" },
      h("h1", { class: "page-header__title" }, title, counter !== undefined && counter !== null ? h("span", { class: "counter" }, ` (${counter})`) : null),
      description ? h("p", { class: "page-header__desc" }, description) : null,
      extra || null,
    ),
    actions && actions.length ? h("div", { class: "page-header__actions" }, actions) : null,
  );
}
