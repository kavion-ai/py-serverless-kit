// breadcrumbs([{ label: "Secrets Manager", href: "#/secrets" }, { label: "prod/db" }]): the last item is the page.

import { h } from "../core/dom.js";

export function breadcrumbs(items) {
  const parts = [];
  items.forEach((item, i) => {
    if (i) parts.push(h("span", { class: "sep", "aria-hidden": "true" }, "›"));
    const last = i === items.length - 1;
    parts.push(last || !item.href
      ? h("span", { class: "here", "aria-current": last ? "page" : undefined }, item.label)
      : h("a", { href: item.href }, item.label));
  });
  return h("nav", { class: "breadcrumbs", "aria-label": "Breadcrumbs" }, parts);
}
