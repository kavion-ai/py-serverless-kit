// Empty bucket and Delete bucket pages (type to confirm, AWS wording).

import { h, mount } from "../core/dom.js";
import { api } from "../core/api.js";
import { navigate, href } from "../core/router.js";
import { plural } from "../core/format.js";
import { alert } from "../components/alert.js";
import { button, link } from "../components/button.js";
import { container, loading } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { confirmPage } from "../components/confirm-page.js";
import { table } from "../components/table.js";
import { flash } from "../components/toast.js";
import { setPage, refreshBuckets } from "./shell.js";
import { bucketCrumbs, bucketHref, bucketPath, loadBucketInfo, showLoadError } from "./common.js";

/** EmptyBucket, or (servers without it) delete every version page by page. */
async function emptyBucket(bucket) {
  try {
    return await api("EmptyBucket", { bucket });
  } catch (e) {
    if (e.code !== "NotImplemented") throw e;
  }
  let deleted = 0;
  const errors = [];
  for (let round = 0; round < 1000; round += 1) {
    const data = await api("ListVersions", { bucket, prefix: "" });
    const items = (data.versions || []).filter((v) => !errors.some((x) => x.key === v.key && x.versionId === v.versionId));
    if (!items.length) break;
    for (let i = 0; i < items.length; i += 200) {
      const chunk = items.slice(i, i + 200);
      for (const v of chunk) {
        const out = await api("DeleteObjects", { bucket, objects: [{ key: v.key, versionId: v.versionId }] });
        if (out.errors && out.errors.length) errors.push({ key: v.key, versionId: v.versionId, code: out.errors[0].code, message: out.errors[0].message });
        else deleted += 1;
      }
    }
    if (!data.truncated) break;
  }
  return { deleted, errors };
}

export async function renderEmpty(ctx) {
  const bucket = ctx.params.bucket;
  const crumbs = bucketCrumbs(bucket, "", { label: "Empty bucket" });
  setPage({ crumbs, title: "Empty bucket", content: loading() });
  const body = h("div", { class: "stack" });
  const page = h(
    "div",
    { class: "stack form-page" },
    pageHeader({ title: "Empty bucket" }),
    alert(
      { type: "warning" },
      h("ul", { class: "plain-list" },
        h("li", {}, "Emptying the bucket deletes all objects in the bucket and cannot be undone."),
        h("li", {}, "Objects added to the bucket while the empty bucket action is in progress might be deleted."),
        h("li", {}, "To prevent new objects from being added to this bucket while the empty bucket action is in progress, you might need to update your bucket policy to stop objects from being added to the bucket."),
      ),
    ),
    alert(
      { type: "info" },
      "If your bucket contains a large number of objects, creating a lifecycle rule to delete all objects in the bucket might be a more efficient way of emptying your bucket. ",
      link("Go to lifecycle rule configuration", href(bucketPath(bucket, "/lifecycle/create"))),
    ),
    body,
  );
  mount(
    body,
    confirmPage({
      heading: `Permanently delete all objects in bucket "${bucket}"?`,
      expected: "permanently delete",
      confirmLabel: "Empty",
      variant: "primary",
      cancelHref: bucketHref(bucket),
      onConfirm: async () => {
        const result = await emptyBucket(bucket);
        if (!ctx.alive()) return;
        showEmptyResult(bucket, body, result);
      },
    }),
  );
  setPage({ crumbs, title: "Empty bucket", content: page });
}

function showEmptyResult(bucket, body, result) {
  const errors = result.errors || [];
  refreshBuckets().catch(() => undefined);
  const summary = container(
    { title: "Summary" },
    h(
      "div",
      { class: "summary" },
      h("div", { class: "summary__item" }, h("div", { class: "summary__label" }, "Source"), h("div", {}, `s3://${bucket}`)),
      h("div", { class: "summary__item is-success" }, h("div", { class: "summary__label" }, "Successfully deleted"), h("div", {}, plural(result.deleted || 0, "object"))),
      h("div", { class: ["summary__item", errors.length ? "is-error" : ""] }, h("div", { class: "summary__label" }, "Failed to delete"), h("div", {}, plural(errors.length, "object"))),
    ),
  );
  const parts = [
    errors.length
      ? alert({ type: "error", title: "Some objects could not be deleted" }, "Versions under Object Lock retention or legal hold are kept. Remove the hold or wait for the retention period to end, then try again.")
      : alert({ type: "success", title: `Successfully emptied bucket "${bucket}"` }, "All objects, versions, delete markers and unfinished multipart uploads were removed."),
    summary,
  ];
  if (errors.length) {
    const tbl = table({
      ariaLabel: "Failed to delete",
      rowKey: (e) => `${e.key}\u0000${e.versionId}`,
      pageSize: 25,
      columns: [
        { id: "key", header: "Name", cell: (e) => e.key },
        { id: "version", header: "Version ID", cell: (e) => e.versionId || "-" },
        { id: "error", header: "Error", cell: (e) => `${e.message || ""} (${e.code || "Error"})` },
      ],
      rows: errors,
    });
    parts.push(container({ title: "Failed to delete", counter: errors.length }, tbl.el));
  }
  parts.push(h("div", { class: "form-actions" }, button({ label: "Exit", variant: "primary", href: bucketHref(bucket) })));
  mount(body, ...parts);
}

export async function renderDelete(ctx) {
  const bucket = ctx.params.bucket;
  const crumbs = bucketCrumbs(bucket, "", { label: "Delete bucket" });
  setPage({ crumbs, title: "Delete bucket", content: loading() });
  let info;
  try {
    info = await loadBucketInfo(bucket);
  } catch (e) {
    if (ctx.alive()) showLoadError(e, crumbs);
    return;
  }
  if (!ctx.alive()) return;
  const notEmpty = (info.stats && (info.stats.versions > 0 || info.stats.uploads > 0)) || false;
  setPage({
    crumbs,
    title: "Delete bucket",
    content: h(
      "div",
      { class: "stack form-page" },
      pageHeader({ title: "Delete bucket" }),
      notEmpty
        ? alert(
            { type: "error", title: "This bucket is not empty", action: button({ label: "Empty bucket", href: href(bucketPath(bucket, "/empty")) }) },
            "Buckets must be empty before they can be deleted. To delete all objects in the bucket, use the empty bucket configuration.",
          )
        : null,
      alert(
        { type: "warning" },
        h("ul", { class: "plain-list" },
          h("li", {}, "Deleting a bucket cannot be undone."),
          h("li", {}, "Bucket names are unique. If you delete a bucket, another user can create a bucket with the same name."),
        ),
      ),
      confirmPage({
        heading: `Delete bucket "${bucket}"?`,
        intro: ["To confirm deletion, enter the name of the bucket in the text input field."],
        expected: bucket,
        placeholder: bucket,
        confirmLabel: "Delete bucket",
        variant: "danger",
        disabled: notEmpty,
        cancelHref: bucketHref(bucket),
        onConfirm: async () => {
          await api("DeleteBucket", { bucket });
          await refreshBuckets().catch(() => undefined);
          flash("success", "", { title: `Successfully deleted bucket "${bucket}"` });
          navigate("/buckets");
        },
      }),
    ),
  });
}
