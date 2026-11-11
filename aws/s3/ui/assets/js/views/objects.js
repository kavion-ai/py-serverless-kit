// The Objects tab: toolbar, "Find objects by prefix", "Show versions", the objects table and drag-and-drop upload.

import { h } from "../core/dom.js";
import { state } from "../core/state.js";
import { api, errorText } from "../core/api.js";
import { navigate } from "../core/router.js";
import { formatBytes, formatDate, fileType, storageClassLabel, ARCHIVED_CLASSES } from "../core/format.js";
import { s3Uri, objectUrl } from "../core/s3.js";
import { table } from "../components/table.js";
import { button, iconButton, link } from "../components/button.js";
import { container, emptyState } from "../components/container.js";
import { dropdown } from "../components/dropdown.js";
import { toggle } from "../components/toggle.js";
import { icon } from "../components/icons.js";
import { pill } from "../components/badge.js";
import { errorSlot } from "../components/alert.js";
import { copyWithToast } from "../components/copy-button.js";
import { bucketHref, bucketPath, objectHref } from "./common.js";
import { collectDropped } from "./upload.js";
import { runOpen, runDownload, shareModal, copyMoveModal, renameModal, totalSizeModal, restoreModal, createFolderModal } from "./object-actions.js";

export async function renderObjectsTab({ ctx, bucket, info, body, prefix }) {
  const versioned = Boolean(info.versioning);
  let showVersions = versioned && ctx.query.versions === "1";
  let search = "";
  let next = "";
  let selected = [];
  let rows = [];
  const errors = errorSlot();
  const counter = h("span", {});

  // ------------------------------------------------------------------ toolbar
  const files = () => selected.filter((r) => r.kind !== "folder" && !r.deleteMarker);
  const versionOf = (r) => (showVersions && r.versionId && !r.latest ? r.versionId : "");
  const btnRefresh = iconButton("refresh", "Refresh", () => load());
  const btnUri = button({ label: "Copy S3 URI", icon: "copy", onClick: () => copyWithToast(selected.map((r) => s3Uri(bucket, r.key)).join("\n"), selected.length > 1 ? "S3 URIs copied" : "S3 URI copied") });
  const btnUrl = button({
    label: "Copy URL",
    icon: "copy",
    onClick: () => copyWithToast(files().map((r) => objectUrl(bucket, r.key) + (versionOf(r) ? `?versionId=${encodeURIComponent(r.versionId)}` : "")).join("\n"), "URL copied"),
  });
  const btnDownload = button({ label: "Download", icon: "download", onClick: () => runDownload(bucket, files()[0].key, versionOf(files()[0])) });
  const btnOpen = button({ label: "Open", icon: "external", onClick: () => runOpen(bucket, files()[0].key, versionOf(files()[0])) });
  const btnDelete = button({ label: "Delete", onClick: () => goDelete() });
  const actions = dropdown({
    label: "Actions",
    items: () => {
      const one = files().length === 1 && selected.length === 1 ? files()[0] : null;
      const anyFolder = selected.some((r) => r.kind === "folder");
      const allFiles = selected.length > 0 && files().length === selected.length;
      const plain = !showVersions || selected.every((r) => r.kind === "folder" || r.latest);
      return [
        { label: "Copy", disabled: !selected.length || !plain, onClick: () => copyMoveModal({ bucket, prefix, items: selected.map(item), move: false, onDone: load }) },
        { label: "Move", disabled: !selected.length || !plain, onClick: () => copyMoveModal({ bucket, prefix, items: selected.map(item), move: true, onDone: load }) },
        { label: "Rename object", disabled: !one || !plain, onClick: () => renameModal({ bucket, key: one.key, onDone: load }) },
        { divider: true },
        { label: "Edit storage class", disabled: !allFiles || !plain, onClick: () => editStorageClass() },
        { label: "Edit metadata", disabled: !one || !plain, onClick: () => navigate(bucketPath(bucket, "/object/edit/metadata"), { key: one.key }) },
        { label: "Edit tags", disabled: !one, onClick: () => navigate(bucketPath(bucket, "/object/edit/tags"), { key: one.key, versionId: versionOf(one) }) },
        { divider: true },
        { label: "Share with a presigned URL", disabled: !one, onClick: () => shareModal({ bucket, key: one.key, versionId: versionOf(one) }) },
        { label: "Calculate total size", disabled: !selected.length || (showVersions && !anyFolder && !allFiles), onClick: () => totalSizeModal({ bucket, items: selected.map(item) }) },
        {
          label: "Initiate restore",
          disabled: !one || !ARCHIVED_CLASSES.includes(one.storageClass),
          onClick: () => restoreModal({ bucket, key: one.key, versionId: versionOf(one), onDone: load }),
        },
      ];
    },
  });
  const btnFolder = button({ label: "Create folder", icon: "folder", onClick: () => createFolderModal({ bucket, prefix, onDone: load }) });
  const btnUpload = button({ label: "Upload", icon: "upload", variant: "primary", onClick: () => navigate(bucketPath(bucket, "/upload"), { prefix }) });

  function item(r) {
    return { key: r.key, folder: r.kind === "folder", size: r.size };
  }

  function updateButtons() {
    const f = files();
    btnUri.disabled = !selected.length;
    btnUrl.disabled = !f.length || f.length !== selected.length;
    btnDownload.disabled = btnOpen.disabled = !(f.length === 1 && selected.length === 1);
    btnDelete.disabled = !selected.length;
    actions.setDisabled(!selected.length);
  }

  function goDelete() {
    state.pendingDelete = {
      bucket,
      prefix,
      versions: showVersions,
      items: selected.map((r) => ({ key: r.key, versionId: showVersions ? r.versionId || "" : "", folder: r.kind === "folder", deleteMarker: Boolean(r.deleteMarker), size: r.size })),
    };
    navigate(bucketPath(bucket, "/delete-objects"), { prefix });
  }

  function editStorageClass() {
    const keys = files().map((r) => r.key);
    if (keys.length === 1) {
      navigate(bucketPath(bucket, "/object/edit/storage-class"), { key: keys[0] });
      return;
    }
    state.pendingKeys = { bucket, prefix, keys };
    navigate(bucketPath(bucket, "/object/edit/storage-class"), { multi: "1" });
  }

  // ------------------------------------------------------------------ table
  const rel = (key) => (key.startsWith(prefix) ? key.slice(prefix.length) : key);
  const nameCell = (r) => {
    if (r.kind === "folder") {
      return link([icon("folder", { size: 16, className: "obj-icon obj-icon--folder" }), rel(r.key)], bucketHref(bucket, { prefix: r.key }), { className: "obj-name" });
    }
    if (showVersions && !r.first) {
      return h("span", { class: "obj-name obj-name--version" }, h("span", { class: "obj-branch", "aria-hidden": "true" }, "└"), r.deleteMarker ? rel(r.key) : link(rel(r.key), objectHref(bucket, r.key, r.versionId)));
    }
    const label = [icon(r.deleteMarker ? "trash" : "file", { size: 16, className: "obj-icon" }), rel(r.key)];
    if (r.deleteMarker) return h("span", { class: "obj-name is-muted" }, label);
    return link(label, objectHref(bucket, r.key, showVersions && !r.latest ? r.versionId : ""), { className: "obj-name" });
  };
  const columns = () => {
    const cols = [{ id: "name", header: "Name", cell: nameCell, sortValue: showVersions ? null : (r) => (r.kind === "folder" ? "\u0000" : "") + rel(r.key) }];
    cols.push({ id: "type", header: "Type", cell: (r) => (r.kind === "folder" ? "Folder" : r.deleteMarker ? "Delete marker" : fileType(r.key)), sortValue: showVersions ? null : (r) => (r.kind === "folder" ? "" : fileType(r.key)) });
    if (showVersions) {
      cols.push({
        id: "version",
        header: "Version ID",
        cell: (r) => (r.kind === "folder" ? "-" : h("span", { class: "mono small" }, r.versionId || "null", r.latest ? pill("Current", "info") : null)),
      });
    }
    cols.push(
      { id: "modified", header: "Last modified", cell: (r) => (r.kind === "folder" ? "-" : formatDate(r.modified)), sortValue: showVersions ? null : (r) => r.modified || "" },
      { id: "size", header: "Size", align: "right", cell: (r) => (r.kind === "folder" || r.deleteMarker ? "-" : formatBytes(r.size)), sortValue: showVersions ? null : (r) => (r.kind === "folder" ? -1 : Number(r.size)) },
      { id: "class", header: "Storage class", cell: (r) => (r.kind === "folder" || r.deleteMarker ? "-" : storageClassLabel(r.storageClass)) },
    );
    return cols;
  };

  const tableSlot = h("div");
  let tbl = null;
  function buildTable() {
    tbl = table({
      ariaLabel: "Objects",
      columns: columns(),
      selectable: "multi",
      rowKey: (r) => `${r.kind}:${r.key}:${r.versionId || ""}`,
      pageSize: 50,
      loading: true,
      rowClass: (r) => (showVersions && !r.first ? "is-version" : ""),
      onSelect: (list) => {
        selected = list;
        updateButtons();
      },
      empty: () =>
        search
          ? emptyState({ title: "No matches", text: `No objects or folders start with "${search}".` })
          : emptyState({
              title: "No objects",
              text: prefix ? "This folder is empty. Drop files here or choose Upload." : "You don't have any objects in this bucket. Drop files here or choose Upload.",
              action: button({ label: "Upload", icon: "upload", onClick: () => navigate(bucketPath(bucket, "/upload"), { prefix }) }),
            }),
    });
    tableSlot.replaceChildren(tbl.el);
  }

  const more = h("div", { class: "load-more", hidden: true }, button({ label: "Load more objects", onClick: () => load(true) }));

  // ------------------------------------------------------------------ loading
  function toRows(data) {
    const listPrefix = prefix + search;
    const out = [];
    if (!showVersions) {
      for (const f of data.folders || []) out.push({ kind: "folder", key: f });
      for (const o of data.objects || []) {
        if (o.key === prefix) continue;
        out.push({ kind: "object", key: o.key, size: o.size, modified: o.modified, storageClass: o.class, latest: true, versionId: o.versionId });
      }
      return out;
    }
    let folders = data.folders;
    let versions = data.versions || [];
    if (!Array.isArray(folders)) {
      const set = new Set();
      versions = versions.filter((v) => {
        const rest = v.key.slice(listPrefix.length);
        const i = rest.indexOf("/");
        if (i >= 0 && i < rest.length - 1) {
          set.add(listPrefix + rest.slice(0, i + 1));
          return false;
        }
        if (i === rest.length - 1 && rest.length > 0 && v.key !== prefix) {
          set.add(v.key);
          return false;
        }
        return true;
      });
      folders = [...set].sort();
    }
    for (const f of folders) out.push({ kind: "folder", key: f });
    let lastKey = null;
    for (const v of versions) {
      if (v.key === prefix) continue;
      out.push({
        kind: "version",
        key: v.key,
        versionId: v.versionId,
        latest: v.latest,
        deleteMarker: v.deleteMarker,
        size: v.size,
        modified: v.modified,
        storageClass: v.class,
        first: v.key !== lastKey,
      });
      lastKey = v.key;
    }
    return out;
  }

  async function load(append) {
    errors.set(null);
    if (!append) {
      buildTable();
      next = "";
    }
    more.hidden = true;
    try {
      let data;
      if (showVersions) {
        data = await api("ListVersions", { bucket, prefix: prefix + search, delimiter: "/" });
        data.next = "";
        if (data.truncated) errors.set("Only the first 2,000 versions are shown. Narrow the list with Find objects by prefix.", "List truncated");
      } else {
        data = await api("ListObjects", { bucket, prefix: prefix + search, delimiter: "/", token: append ? next : "", max: 1000 });
      }
      if (!ctx.alive()) return;
      const fresh = toRows(data);
      rows = append ? rows.concat(fresh) : fresh;
      next = data.next || "";
      tbl.setRows(rows, { keepSelection: Boolean(append), keepPage: Boolean(append) });
      counter.textContent = ` (${rows.length}${next ? "+" : ""})`;
      more.hidden = !next;
    } catch (e) {
      if (!ctx.alive()) return;
      tbl.setRows([]);
      errors.set(errorText(e));
    }
  }

  // ------------------------------------------------------------------ search, versions toggle
  const searchInput = h("input", {
    class: "input",
    type: "search",
    placeholder: "Find objects by prefix",
    "aria-label": "Find objects by prefix",
  });
  let timer = 0;
  searchInput.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      search = searchInput.value;
      load();
    }, 350);
  });
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      clearTimeout(timer);
      search = searchInput.value;
      load();
    }
  });
  const versionsToggle = versioned
    ? toggle({
        label: "Show versions",
        checked: showVersions,
        onChange: (on) => {
          showVersions = on;
          history.replaceState(null, "", bucketHref(bucket, { prefix, versions: on ? "1" : "" }));
          load();
        },
      })
    : null;

  // ------------------------------------------------------------------ drag and drop
  const dropOverlay = h("div", { class: "drop-overlay", hidden: true }, h("div", { class: "drop-overlay__box" }, icon("upload", { size: 28 }), h("div", {}, "Drop files and folders to upload them to"), h("div", { class: "mono" }, s3Uri(bucket, prefix))));
  let depth = 0;
  const hasFiles = (e) => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
  const wrap = h("div", { class: "objects-tab" });
  wrap.addEventListener("dragenter", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth += 1;
    dropOverlay.hidden = false;
  });
  wrap.addEventListener("dragover", (e) => {
    if (hasFiles(e)) e.preventDefault();
  });
  wrap.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) dropOverlay.hidden = true;
  });
  wrap.addEventListener("drop", async (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    dropOverlay.hidden = true;
    const dropped = await collectDropped(e.dataTransfer);
    if (!dropped.length) return;
    state.pendingUpload = { bucket, prefix, files: dropped };
    navigate(bucketPath(bucket, "/upload"), { prefix });
  });

  wrap.append(
    errors,
    container(
      {
        title: h("span", {}, "Objects", counter),
        description: "Objects are the fundamental entities stored in a bucket. To let others access your objects, grant them permissions with a bucket policy or share a presigned URL.",
        actions: [btnRefresh, btnUri, btnUrl, btnDownload, btnOpen, btnDelete, actions, btnFolder, btnUpload],
      },
      h("div", { class: "objects-toolbar" }, h("div", { class: "objects-search" }, icon("search", { size: 14, className: "objects-search__icon" }), searchInput), versionsToggle),
      tableSlot,
      more,
    ),
    dropOverlay,
  );
  body.replaceChildren(wrap);
  updateButtons();
  await load();
}
