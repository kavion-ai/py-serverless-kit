// Edit bucket policy: Bucket ARN, JSON editor with live validation, and a "Policy examples" list.

import { h } from "../core/dom.js";
import { api, errorText } from "../core/api.js";
import { navigate } from "../core/router.js";
import { button, busy } from "../components/button.js";
import { container, loading, formActions } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { alert, errorSlot } from "../components/alert.js";
import { jsonEditor, prettyJson } from "../components/json-editor.js";
import { copyable } from "../components/copy-button.js";
import { confirmModal } from "../components/modal.js";
import { flash } from "../components/toast.js";
import { POLICY_EXAMPLES, checkPolicy } from "../examples/policy-examples.js";
import { setPage, refreshBuckets } from "./shell.js";
import { bucketCrumbs, bucketHref, bucketPath, editHref, loadBucketInfo, showLoadError } from "./common.js";

export async function render(ctx) {
  const bucket = ctx.params.bucket;
  const back = bucketHref(bucket, { tab: "permissions" });
  const title = "Edit bucket policy";
  const crumbs = bucketCrumbs(bucket, "", { label: "Permissions", href: back }, { label: title });
  setPage({ crumbs, title, content: loading() });
  let info;
  try {
    info = await loadBucketInfo(bucket);
  } catch (e) {
    if (ctx.alive()) showLoadError(e, crumbs);
    return;
  }
  if (!ctx.alive()) return;

  const vars = { bucket, arn: info.arn, account: info.account };
  const preset = POLICY_EXAMPLES.find((x) => x.id === ctx.query.example);
  const initial = preset ? JSON.stringify(preset.build(vars), null, 2) : info.policy ? prettyJson(info.policy) : "";
  const editor = jsonEditor({ value: initial, rows: 22, allowEmpty: true, ariaLabel: "Bucket policy", validate: (p) => checkPolicy(p) });
  const errors = errorSlot();

  const publicBlocked = info.publicBlock.BlockPublicPolicy;
  const notes = [];
  if (preset) notes.push(alert({ type: "info", dismissible: true }, `The example "${preset.title}" was inserted. Review it, then choose Save changes.`));
  if (publicBlocked) {
    notes.push(
      alert(
        { type: "warning", title: "Block public access is on for bucket policies" },
        "Policies that grant public access (Principal \"*\" without an IP or account condition) are refused while BlockPublicPolicy is on. ",
        button({ label: "Edit Block public access", variant: "inline", href: editHref(bucket, "public-access") }),
      ),
    );
  }

  const examples = h(
    "ul",
    { class: "examples" },
    POLICY_EXAMPLES.map((ex) =>
      h(
        "li",
        { class: "examples__item" },
        h("div", { class: "examples__text" }, h("div", { class: "strong" }, ex.title), h("div", { class: "muted small" }, ex.description)),
        button({
          label: "Use",
          onClick: async () => {
            const current = editor.getValue().trim();
            if (current && current !== initial.trim()) {
              const ok = await confirmModal({ title: "Replace the policy?", message: "The example replaces what is in the editor.", confirmLabel: "Replace" });
              if (!ok) return;
            }
            editor.setValue(JSON.stringify(ex.build(vars), null, 2));
            editor.focus();
          },
        }),
      ),
    ),
  );

  const save = button({ label: "Save changes", variant: "primary" });
  save.addEventListener("click", () =>
    busy(save, async () => {
      errors.set(null);
      try {
        if (!editor.isValid()) throw new Error("Fix the policy before saving.");
        const text = editor.getValue().trim();
        if (!text && !info.policy) {
          navigate(bucketPath(bucket), { tab: "permissions" });
          return;
        }
        await api("PutBucketSetting", { bucket, setting: "policy", value: text ? JSON.stringify(JSON.parse(text)) : "" });
        refreshBuckets().catch(() => undefined);
        flash("success", "", { title: text ? "Successfully edited bucket policy" : "Successfully deleted bucket policy" });
        navigate(bucketPath(bucket), { tab: "permissions" });
      } catch (e) {
        errors.set(errorText(e), "Failed to save the bucket policy");
      }
    }),
  );

  setPage({
    crumbs,
    title,
    content: h(
      "div",
      { class: "stack form-page form-page--wide" },
      pageHeader({ title, description: "The bucket policy, written in JSON, provides access to the objects stored in the bucket. Signed requests are allowed unless a Deny statement matches; anonymous requests need an Allow." }),
      notes,
      h(
        "div",
        { class: "editor-layout" },
        container(
          { title: "Bucket policy", description: "Leave the editor empty to delete the policy." },
          h("div", { class: "field" }, h("div", { class: "field__label" }, "Bucket ARN"), copyable(info.arn, { mono: true, title: "Copy bucket ARN" })),
          h("div", { class: "field" }, h("div", { class: "field__label" }, "Policy"), editor.el),
        ),
        container({ title: "Policy examples", description: "Choose an example to put it in the editor with this bucket's ARN filled in." }, examples),
      ),
      errors,
      formActions(button({ label: "Cancel", variant: "link", href: back }), save),
    ),
  });
}
