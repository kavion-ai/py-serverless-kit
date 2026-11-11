// Object edit pages: Edit storage class (one or several objects), Edit metadata, Edit tags.

import { h, mount } from "../core/dom.js";
import { state } from "../core/state.js";
import { api, errorText } from "../core/api.js";
import { navigate } from "../core/router.js";
import { baseName, parentPrefix, plural, STORAGE_CLASSES } from "../core/format.js";
import { s3Uri } from "../core/s3.js";
import { button, busy } from "../components/button.js";
import { container, loading, formActions } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { radioGroup, select, input } from "../components/field.js";
import { alert, errorSlot } from "../components/alert.js";
import { tagEditor } from "../components/tag-editor.js";
import { flash } from "../components/toast.js";
import { setPage } from "./shell.js";
import { bucketCrumbs, bucketHref, bucketPath, objectHref, showLoadError } from "./common.js";

const SYSTEM_KEYS = ["Content-Type", "Cache-Control", "Content-Disposition", "Content-Encoding", "Content-Language", "Expires"];
const TITLES = { "storage-class": "Edit storage class", metadata: "Edit metadata", tags: "Edit tags" };

export async function render(ctx) {
  const bucket = ctx.params.bucket;
  const what = ctx.params.what;
  const title = TITLES[what];
  if (!title) {
    navigate(bucketPath(bucket), {}, { replace: true });
    return;
  }
  const multi = ctx.query.multi === "1" && state.pendingKeys && state.pendingKeys.bucket === bucket ? state.pendingKeys : null;
  const keys = multi ? multi.keys : ctx.query.key ? [ctx.query.key] : [];
  if (!keys.length) {
    navigate(bucketPath(bucket), {}, { replace: true });
    return;
  }
  const key = keys[0];
  const versionId = ctx.query.versionId || "";
  const folder = multi ? multi.prefix : parentPrefix(key);
  const crumbs = multi ? bucketCrumbs(bucket, folder, { label: title }) : bucketCrumbs(bucket, folder, { label: baseName(key), href: objectHref(bucket, key, versionId) }, { label: title });
  const back = multi ? bucketHref(bucket, { prefix: folder }) : objectHref(bucket, key, versionId);
  setPage({ crumbs, title, content: loading() });

  let heads;
  try {
    heads = await Promise.all(keys.map((k) => api("HeadObject", { bucket, key: k, versionId: keys.length === 1 ? versionId : "" })));
  } catch (e) {
    if (ctx.alive()) showLoadError(e, crumbs, "The object could not be loaded");
    return;
  }
  if (!ctx.alive()) return;

  const errors = errorSlot();
  const save = button({ label: "Save changes", variant: "primary" });
  let section;
  let submit;

  if (what === "storage-class") {
    const current = heads.length === 1 ? heads[0].class : "";
    const picker = radioGroup({ ariaLabel: "Storage class", value: current || "STANDARD", items: STORAGE_CLASSES.map((c) => ({ value: c.value, label: c.label, description: c.description })) });
    section = [
      alert({ type: "info" }, "Changing the storage class writes the object again with the new class (a new version when versioning is on). Its metadata and tags are kept."),
      multi ? container({ title: "Objects", counter: keys.length }, h("ul", { class: "plain-list mono small" }, keys.slice(0, 20).map((k) => h("li", {}, s3Uri(bucket, k))), keys.length > 20 ? h("li", {}, `and ${keys.length - 20} more`) : null)) : null,
      container({ title: "Storage class", description: "Choose a storage class based on your use case and access requirements." }, picker),
    ];
    submit = async () => {
      const failed = [];
      for (const o of heads) {
        try {
          await api("UpdateMeta", { bucket, key: o.key, type: o.type, headers: o.headers || {}, meta: o.meta || {}, class: picker.value });
        } catch (e) {
          failed.push(`${o.key}: ${errorText(e)}`);
        }
      }
      if (failed.length) throw new Error(`Some objects could not be changed: ${failed.join("; ")}`);
      flash("success", "", { title: `Successfully edited the storage class of ${plural(heads.length, "object")}` });
      state.pendingKeys = null;
      navigate(multi ? bucketPath(bucket) : bucketPath(bucket, "/object"), multi ? { prefix: folder } : { key });
    };
  } else if (what === "metadata") {
    const o = heads[0];
    const rows = h("div", { class: "meta-editor__rows" });
    const addRow = (type, k, v) => {
      const typeSel = select({ options: ["System defined", "User defined"], value: type, ariaLabel: "Type" });
      const keyBox = h("div", { class: "meta-editor__key" });
      const value = input({ value: v || "", "aria-label": "Value", placeholder: "Value" });
      let keyControl;
      const drawKey = (initial) => {
        if (typeSel.value === "System defined") {
          keyControl = select({ options: SYSTEM_KEYS, value: SYSTEM_KEYS.includes(initial) ? initial : SYSTEM_KEYS[1], ariaLabel: "Key" });
          mount(keyBox, keyControl);
        } else {
          keyControl = input({ value: initial || "", placeholder: "name", "aria-label": "Key" });
          mount(keyBox, h("div", { class: "input-prefix" }, h("span", {}, "x-amz-meta-"), keyControl));
        }
      };
      typeSel.addEventListener("change", () => drawKey(""));
      drawKey(k);
      const row = h("div", { class: "meta-editor__row" }, typeSel, keyBox, value, button({ label: "Remove", onClick: () => row.remove() }));
      row.read = () => ({ type: typeSel.value, key: keyControl.value.trim(), value: value.value });
      rows.append(row);
    };
    addRow("System defined", "Content-Type", o.type || "");
    for (const [k, v] of Object.entries(o.headers || {})) {
      const name = SYSTEM_KEYS.find((s) => s.toLowerCase() === k.toLowerCase()) || k;
      addRow("System defined", name, v);
    }
    for (const [k, v] of Object.entries(o.meta || {})) addRow("User defined", k, v);
    section = [
      alert({ type: "info" }, "Saving writes the object again with the new metadata (a new version when versioning is on). Tags and the storage class are kept."),
      container(
        { title: "Metadata", description: "Metadata is optional information provided as a name-value (key-value) pair. System-defined metadata are standard HTTP headers; user-defined metadata are returned as x-amz-meta-* headers." },
        h("div", { class: "meta-editor" }, h("div", { class: "meta-editor__head" }, h("div", {}, "Type"), h("div", {}, "Key"), h("div", {}, "Value"), h("div")), rows),
        h("div", { class: "btn-row" }, button({ label: "Add metadata", onClick: () => addRow("User defined", "", "") })),
      ),
    ];
    submit = async () => {
      let type = "";
      const headers = {};
      const meta = {};
      const seen = new Set();
      for (const row of rows.children) {
        const r = row.read();
        if (!r.key) throw new Error("Enter a key for every metadata row, or remove the empty rows.");
        const id = `${r.type}:${r.key.toLowerCase()}`;
        if (seen.has(id)) throw new Error(`The key ${r.key} is used twice.`);
        seen.add(id);
        if (r.type === "System defined") {
          if (r.key === "Content-Type") type = r.value;
          else headers[r.key] = r.value;
        } else {
          if (!/^[A-Za-z0-9!#$&'*+.^_`|~-]+$/.test(r.key)) throw new Error(`The user-defined key "${r.key}" contains characters that are not allowed in an HTTP header name.`);
          meta[r.key] = r.value;
        }
      }
      await api("UpdateMeta", { bucket, key, type: type || "binary/octet-stream", headers, meta, class: o.class });
      flash("success", "", { title: "Successfully edited metadata" });
      navigate(bucketPath(bucket, "/object"), { key });
    };
  } else {
    const o = heads[0];
    const tags = tagEditor({ tags: o.tags || {}, max: 10, keyMax: 128, valueMax: 256 });
    section = [container({ title: "Tags", description: "You can use object tags to analyze, manage, and specify permissions for objects, and to filter lifecycle rules. Up to 10 tags per object." }, tags.el)];
    submit = async () => {
      if (tags.validate()) return;
      await api("PutObjectTags", { bucket, key, versionId, tags: tags.getValue() });
      flash("success", "", { title: "Successfully edited tags" });
      navigate(bucketPath(bucket, "/object"), { key, versionId });
    };
  }

  save.addEventListener("click", () =>
    busy(save, async () => {
      errors.set(null);
      try {
        await submit();
      } catch (e) {
        errors.set(errorText(e));
      }
    }),
  );
  setPage({
    crumbs,
    title,
    content: h(
      "div",
      { class: "stack form-page" },
      pageHeader({ title, description: multi ? `${plural(keys.length, "object")} in ${s3Uri(bucket, folder)}` : s3Uri(bucket, key) }),
      section,
      errors,
      formActions(button({ label: "Cancel", variant: "link", href: back }), save),
    ),
  });
}
