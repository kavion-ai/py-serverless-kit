// The title row of a page: pageHeader({ title, counter, description, actions: [buttons], extra })

import { h } from "../core/dom.js";

export function pageHeader({ title, counter, description, actions = [], extra } = {}) {
  return h("header", { class: "page-header" },
    h("div", { class: "titles" },
      h("h1", {}, title, counter !== undefined && counter !== null ? h("span", { class: "counter" }, `(${counter})`) : null, extra),
      description ? h("div", { class: "desc" }, description) : null),
    actions.length ? h("div", { class: "btn-group" }, actions) : null);
}
