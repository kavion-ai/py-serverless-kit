// Key-value columns (the "overview" layout of the AWS console).

import { h } from "../core/dom.js";
import { copyButton } from "./copy-button.js";

/** kvList([{label, value, copy, mono}], {columns}) - value can be a node; copy adds a copy button for that text. */
export function kvList(items, { columns = 3 } = {}) {
  return h(
    "dl",
    { class: "kv", style: { "--kv-columns": String(columns) } },
    items
      .filter(Boolean)
      .map((item) =>
        h(
          "div",
          { class: "kv__item" },
          h("dt", {}, item.label),
          h(
            "dd",
            { class: item.mono ? "mono" : "" },
            item.copy ? copyButton(item.copy, { title: `Copy ${item.label}` }) : null,
            item.value === undefined || item.value === null || item.value === "" ? "-" : item.value,
          ),
        ),
      ),
  );
}
