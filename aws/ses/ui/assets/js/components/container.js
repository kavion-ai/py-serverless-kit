// A panel with a header: container({ title, counter, description, actions, footer, flush }, ...body)
// flush: true removes the body padding (tables fill the panel edge to edge).

import { h } from "../core/dom.js";

export function container({ title, counter, description, actions = [], footer, flush = false, id } = {}, ...body) {
  const header = title || actions.length
    ? h("div", { class: "c-header" },
      h("div", { class: "c-titles" },
        title ? h("h2", {}, title,
          counter !== undefined && counter !== null ? h("span", { class: "counter" }, ` (${counter})`) : null) : null,
        description ? h("div", { class: "c-desc" }, description) : null),
      actions.length ? h("div", { class: "btn-group" }, actions) : null)
    : null;
  return h("section", { class: "container", id },
    header,
    h("div", { class: ["c-body", flush && "flush"] }, body),
    footer ? h("div", { class: "c-footer" }, footer) : null);
}
