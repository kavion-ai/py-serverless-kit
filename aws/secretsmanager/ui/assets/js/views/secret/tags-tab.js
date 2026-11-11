// Tags tab: the secret's tags and "Edit tags" (UntagResource for removed keys, then TagResource for the rest).

import { call } from "../../core/api.js";
import { h } from "../../core/dom.js";
import { button } from "../../components/button.js";
import { flash } from "../../components/flash.js";
import { modal } from "../../components/modal.js";
import { table } from "../../components/table.js";
import { tagEditor } from "../../components/tag-editor.js";

export function tagsTab(secret, { onChange } = {}) {
  const tags = secret.Tags || [];
  const t = table({
    title: "Tags",
    actions: [button("Edit tags", { onClick: () => edit() })],
    filter: { placeholder: "Find tags", match: (tag, text) => `${tag.Key} ${tag.Value}`.toLowerCase().includes(text) },
    columns: [
      { id: "key", header: "Key", wrap: true, sort: (tag) => tag.Key, cell: (tag) => tag.Key },
      { id: "value", header: "Value", wrap: true, sort: (tag) => tag.Value, cell: (tag) => tag.Value || h("span", { class: "faint" }, "-") },
    ],
    items: tags,
    trackBy: (tag) => tag.Key,
    pageSize: 20,
    empty: h("div", { class: "table-empty" }, h("b", {}, "No tags"), "No tags are associated with this secret.",
      h("div", {}, button("Add tags", { onClick: () => edit() }))),
  });

  function edit() {
    const editor = tagEditor(tags);
    const error = h("div", { class: "f-error", role: "alert" });
    let m;
    m = modal({
      title: "Edit tags",
      wide: true,
      body: [h("div", { class: "muted" }, "Tags are key/value labels. The secrets list filter matches tag keys and values."), editor.el, error],
      footer: [
        button("Cancel", { variant: "link", onClick: () => m.close() }),
        button("Save", {
          variant: "primary",
          onClick: async () => {
            error.textContent = "";
            let wanted;
            try {
              wanted = editor.value();
            } catch (err) {
              error.textContent = err.message;
              return;
            }
            const gone = tags.map((tag) => tag.Key).filter((k) => !wanted.some((tag) => tag.Key === k));
            try {
              if (gone.length) await call("UntagResource", { SecretId: secret.Name, TagKeys: gone });
              if (wanted.length) await call("TagResource", { SecretId: secret.Name, Tags: wanted });
              m.close();
              flash.success("The tags were saved.");
              if (onChange) onChange();
            } catch (err) {
              error.textContent = err.text || err.message;
            }
          },
        }),
      ],
    });
  }

  return t.el;
}
