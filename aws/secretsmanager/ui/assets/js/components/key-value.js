// Label/value pairs in columns, like the AWS "details" panels:
//   keyValue([[{ label: "Secret name", value: name }], [{ label: "ARN", value: arn, copy: arn, mono: true }]])
// Each inner list is one column; `copy` adds a copy button for that text. `value` may be a node.

import { h } from "../core/dom.js";
import { copyButton } from "./copy-button.js";

export function keyValue(columns) {
  return h("div", { class: "kv-grid" }, columns.map((items) => h("div", { class: "kv-col" }, items.map(kvItem))));
}

export function kvItem({ label, value, copy, mono = false }) {
  const empty = value === undefined || value === null || value === "";
  return h("div", { class: "kv-item" },
    h("div", { class: "kv-label" }, label),
    h("div", { class: "kv-value" },
      copy ? copyButton(copy, { label: `Copy ${label}` }) : null,
      empty ? h("span", { class: "faint" }, "-") : h("span", { class: mono ? "mono" : undefined }, value)));
}
