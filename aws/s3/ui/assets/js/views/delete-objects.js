// Delete objects page: the chosen objects, the right warning (delete markers or permanent deletion), a typed
// confirmation, then a status summary.

import { h, mount } from "../core/dom.js";
import { state } from "../core/state.js";
import { api } from "../core/api.js";
import { navigate } from "../core/router.js";
import { formatBytes, fileType, plural } from "../core/format.js";
import { s3Uri } from "../core/s3.js";
import { table } from "../components/table.js";
import { button } from "../components/button.js";
import { container, loading } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { alert } from "../components/alert.js";
import { confirmPage } from "../components/confirm-page.js";
import { setPage, refreshBuckets } from "./shell.js";
import { bucketCrumbs, bucketHref, bucketPath, loadBucketInfo, showLoadError } from "./common.js";

async function deleteFolderVersions(bucket, prefix, result) {
  for (let round = 0; round < 1000; round += 1) {
    const data = await api("ListVersions", { bucket, prefix });
    const list = (data.versions || []).filter((v) => !result.failedIds.has(`${v.key}\u0000${v.versionId}`));
    if (!list.length) return;
    for (let i = 0; i < list.length; i += 100) {
      const chunk = list.slice(i, i + 100);
      for (const v of chunk) {
        const out = await api("DeleteObjects", { bucket, objects: [{ key: v.key, versionId: v.versionId }] });
        if (out.errors && out.errors.length) {
          result.failedIds.add(`${v.key}\u0000${v.versionId}`);
          result.failed.push({ key: v.key, versionId: v.versionId, code: out.errors[0].code, message: out.errors[0].message });
        } else result.deleted += 1;
      }
    }
  }
}

export async function render(ctx) {
  const bucket = ctx.params.bucket;
  const pending = state.pendingDelete && state.pendingDelete.bucket === bucket ? state.pendingDelete : null;
  const prefix = ctx.query.prefix || (pending ? pending.prefix : "");
  if (!pending || !pending.items.length) {
    navigate(bucketPath(bucket), { prefix }, { replace: true });
    return;
  }
  const crumbs = bucketCrumbs(bucket, prefix, { label: "Delete objects" });
  setPage({ crumbs, title: "Delete objects", content: loading() });
  let info;
  try {
    info = await loadBucketInfo(bucket);
  } catch (e) {
    if (ctx.alive()) showLoadError(e, crumbs);
    return;
  }
  if (!ctx.alive()) return;

  const permanent = pending.versions || !info.versioning;
  const items = pending.items;
  const back = bucketHref(bucket, { prefix, versions: pending.versions ? "1" : "" });
  const tbl = table({
    ariaLabel: "Specified objects",
    rowKey: (i) => `${i.key}\u0000${i.versionId || ""}`,
    pageSize: 25,
    filter: { placeholder: "Find objects by name", match: (i, q) => i.key.toLowerCase().includes(q) },
    columns: [
      { id: "name", header: "Name", cell: (i) => h("span", { class: "mono" }, i.key) },
      pending.versions ? { id: "version", header: "Version ID", cell: (i) => (i.folder ? "-" : h("span", { class: "mono small" }, i.versionId || "null")) } : null,
      { id: "type", header: "Type", cell: (i) => (i.folder ? "Folder" : i.deleteMarker ? "Delete marker" : fileType(i.key)) },
      { id: "size", header: "Size", align: "right", cell: (i) => (i.folder || i.deleteMarker ? "-" : formatBytes(i.size)) },
    ].filter(Boolean),
    rows: items,
  });
  const hasFolder = items.some((i) => i.folder);
  const body = h("div", { class: "stack" });
  const notices = [];
  if (permanent) {
    notices.push(
      alert(
        { type: "warning", title: "Deleting the specified objects can't be undone" },
        pending.versions
          ? "The selected object versions are permanently deleted. Deleting a delete marker makes the previous version of the object current again."
          : "Bucket Versioning is not enabled, so deleted objects cannot be recovered.",
        hasFolder ? h("div", {}, "Every object in the selected folders (and, with versions shown, every version of them) is deleted too.") : null,
      ),
    );
  } else {
    notices.push(
      alert(
        { type: "info" },
        h("ul", { class: "plain-list" },
          h("li", {}, "Deleting the specified objects adds delete markers to them. If you need to undo the delete action, you can delete the delete markers (turn on Show versions)."),
          hasFolder ? h("li", {}, "If a folder is selected for deletion, all objects in the folder are deleted, and any new objects added while the delete action is in progress might also be deleted.") : null,
        ),
      ),
    );
  }

  mount(
    body,
    notices,
    container({ title: "Specified objects", counter: items.length }, tbl.el),
    confirmPage({
      heading: permanent ? "Permanently delete objects?" : "Delete objects?",
      expected: permanent ? "permanently delete" : "delete",
      confirmLabel: "Delete objects",
      variant: "danger",
      cancelHref: back,
      onConfirm: async () => {
        const result = { deleted: 0, failed: [], failedIds: new Set() };
        if (pending.versions) {
          const files = items.filter((i) => !i.folder);
          for (const f of files) {
            const out = await api("DeleteObjects", { bucket, objects: [{ key: f.key, versionId: f.versionId || "null" }] });
            if (out.errors && out.errors.length) result.failed.push({ key: f.key, versionId: f.versionId, code: out.errors[0].code, message: out.errors[0].message });
            else result.deleted += 1;
          }
          for (const f of items.filter((i) => i.folder)) await deleteFolderVersions(bucket, f.key, result);
        } else {
          const out = await api("DeleteObjects", { bucket, objects: items.map((i) => ({ key: i.key, recursive: i.folder })) });
          result.deleted = (out.deleted || []).length;
          result.failed = (out.errors || []).map((e) => ({ key: e.key, versionId: "", code: e.code, message: e.message }));
        }
        state.pendingDelete = null;
        refreshBuckets().catch(() => undefined);
        if (!ctx.alive()) return;
        showResult(result);
      },
    }),
  );

  function showResult(result) {
    const failedTbl = result.failed.length
      ? table({
          ariaLabel: "Failed to delete",
          rowKey: (e) => `${e.key}\u0000${e.versionId || ""}`,
          pageSize: 25,
          columns: [
            { id: "key", header: "Name", cell: (e) => h("span", { class: "mono" }, e.key) },
            { id: "version", header: "Version ID", cell: (e) => e.versionId || "-" },
            { id: "error", header: "Error", cell: (e) => `${e.message} (${e.code})` },
          ],
          rows: result.failed,
        })
      : null;
    setPage({
      crumbs,
      title: "Delete objects: status",
      content: h(
        "div",
        { class: "stack form-page" },
        pageHeader({ title: "Delete objects: status", description: "After you navigate away from this page, the following information is no longer available.", actions: [button({ label: "Close", variant: "primary", href: back })] }),
        result.failed.length
          ? alert({ type: "error", title: "Some objects could not be deleted" }, "See the list below. Versions under Object Lock retention or legal hold cannot be deleted.")
          : alert({ type: "success", title: "Successfully deleted objects" }, `${plural(result.deleted, permanent ? "item" : "object")} deleted from ${s3Uri(bucket, prefix)}.`),
        container(
          { title: "Summary" },
          h(
            "div",
            { class: "summary" },
            h("div", { class: "summary__item" }, h("div", { class: "summary__label" }, "Source"), h("div", { class: "mono" }, s3Uri(bucket, prefix))),
            h("div", { class: "summary__item is-success" }, h("div", { class: "summary__label" }, "Successfully deleted"), h("div", {}, plural(result.deleted, "item"))),
            h("div", { class: ["summary__item", result.failed.length ? "is-error" : ""] }, h("div", { class: "summary__label" }, "Failed to delete"), h("div", {}, plural(result.failed.length, "item"))),
          ),
        ),
        failedTbl ? container({ title: "Failed to delete", counter: result.failed.length }, failedTbl.el) : null,
      ),
    });
  }

  setPage({
    crumbs,
    title: "Delete objects",
    content: h("div", { class: "stack form-page" }, pageHeader({ title: "Delete objects" }), body),
  });
}
