// Breadcrumbs: [{label, href}] - the last item is the current page.

import { h } from "../core/dom.js";
import { icon } from "./icons.js";

export function breadcrumbs(items) {
  return h(
    "nav",
    { class: "crumbs", "aria-label": "Breadcrumbs" },
    h(
      "ol",
      {},
      items.map((item, i) => {
        const last = i === items.length - 1;
        return h(
          "li",
          {},
          last || !item.href ? h("span", { class: "crumbs__current", "aria-current": last ? "page" : undefined }, item.label) : h("a", { href: item.href }, item.label),
          last ? null : icon("caret-right", { size: 12, className: "crumbs__sep" }),
        );
      }),
    ),
  );
}
