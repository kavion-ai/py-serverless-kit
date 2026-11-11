// Upload page: drop zone, Add files / Add folder, the files table, destination and storage class, then the
// "Upload: status" view with per-file progress.

import { h, mount } from "../core/dom.js";
import { state } from "../core/state.js";
import { uploadFile, errorText } from "../core/api.js";
import { formatBytes, fileType, plural, STORAGE_CLASSES, parentPrefix, baseName } from "../core/format.js";
import { s3Uri } from "../core/s3.js";
import { table } from "../components/table.js";
import { button } from "../components/button.js";
import { container, expandable, emptyState, formActions } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { kvList } from "../components/kv-list.js";
import { radioGroup } from "../components/field.js";
import { alert } from "../components/alert.js";
import { badge } from "../components/badge.js";
import { icon } from "../components/icons.js";
import { setPage, refreshBuckets } from "./shell.js";
import { bucketCrumbs, bucketHref, loadBucketInfo } from "./common.js";

/**
 * Files from a drop (folders walked recursively): [{file, path}]. The DataTransfer entries are read synchronously
 * first, because they become unusable once the drop event handler returns.
 */
export function collectDropped(dt) {
  const entries = Array.from(dt.items || [])
    .filter((i) => i.kind === "file")
    .map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null));
  const plainFiles = Array.from(dt.files || []);
  if (!entries.length || entries.some((e) => !e)) return Promise.resolve(plainFiles.map((file) => ({ file, path: file.name })));
  const out = [];
  const walk = (entry, path) =>
    new Promise((resolve) => {
      if (entry.isFile) {
        entry.file(
          (file) => {
            out.push({ file, path: path + file.name });
            resolve();
          },
          () => resolve(),
        );
      } else if (entry.isDirectory) {
        const reader = entry.createReader();
        const all = [];
        const batch = () =>
          reader.readEntries(
            async (list) => {
              if (!list.length) {
                for (const child of all) await walk(child, `${path}${entry.name}/`);
                resolve();
              } else {
                all.push(...list);
                batch();
              }
            },
            () => resolve(),
          );
        batch();
      } else resolve();
    });
  return (async () => {
    for (const e of entries) await walk(e, "");
    return out;
  })();
}

let nextId = 1;

export async function render(ctx) {
  const bucket = ctx.params.bucket;
  const prefix = ctx.query.prefix || "";
  const crumbs = bucketCrumbs(bucket, prefix, { label: "Upload" });
  let queue = [];
  if (state.pendingUpload && state.pendingUpload.bucket === bucket && state.pendingUpload.prefix === prefix) {
    queue = state.pendingUpload.files.map((f) => ({ id: nextId++, file: f.file, path: f.path }));
  }
  state.pendingUpload = null;

  const counter = h("span", {});
  const removeBtn = button({ label: "Remove", disabled: true });
  const fileInput = h("input", { type: "file", multiple: true, hidden: true });
  const dirInput = h("input", { type: "file", multiple: true, webkitdirectory: true, hidden: true });
  const uploadBtn = button({ label: "Upload", variant: "primary", disabled: true });
  let selected = [];

  const tbl = table({
    ariaLabel: "Files and folders",
    selectable: "multi",
    rowKey: (q) => String(q.id),
    pageSize: 50,
    filter: { placeholder: "Find by name", match: (q, t) => q.path.toLowerCase().includes(t) },
    onSelect: (list) => {
      selected = list;
      removeBtn.disabled = !list.length;
    },
    columns: [
      { id: "name", header: "Name", sortValue: (q) => baseName(q.path), cell: (q) => baseName(q.path) },
      { id: "folder", header: "Folder", sortValue: (q) => parentPrefix(q.path), cell: (q) => parentPrefix(q.path) || "-" },
      { id: "type", header: "Type", sortValue: (q) => q.file.type, cell: (q) => q.file.type || fileType(q.path) },
      { id: "size", header: "Size", align: "right", sortValue: (q) => q.file.size, cell: (q) => formatBytes(q.file.size) },
    ],
    empty: () => emptyState({ title: "No files or folders", text: "You have not chosen any files or folders to upload." }),
  });

  function refresh() {
    const total = queue.reduce((n, q) => n + q.file.size, 0);
    counter.textContent = ` (${queue.length} Total, ${formatBytes(total)})`;
    tbl.setRows(queue);
    uploadBtn.disabled = !queue.length;
  }

  function add(list) {
    const known = new Set(queue.map((q) => q.path));
    for (const { file, path } of list) {
      if (known.has(path)) queue = queue.filter((q) => q.path !== path);
      queue.push({ id: nextId++, file, path });
    }
    refresh();
  }

  fileInput.addEventListener("change", () => {
    add(Array.from(fileInput.files).map((file) => ({ file, path: file.name })));
    fileInput.value = "";
  });
  dirInput.addEventListener("change", () => {
    add(Array.from(dirInput.files).map((file) => ({ file, path: file.webkitRelativePath || file.name })));
    dirInput.value = "";
  });
  removeBtn.addEventListener("click", () => {
    const ids = new Set(selected.map((q) => q.id));
    queue = queue.filter((q) => !ids.has(q.id));
    refresh();
  });

  const drop = h(
    "div",
    { class: "dropzone", tabindex: "0", role: "button", "aria-label": "Add files" },
    icon("upload", { size: 28 }),
    h("div", { class: "dropzone__text" }, "Drag and drop files and folders you want to upload here, or choose ", h("b", {}, "Add files"), " or ", h("b", {}, "Add folder"), "."),
  );
  drop.addEventListener("click", () => fileInput.click());
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  const page = h("div", { class: "stack form-page" });
  page.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("is-over");
  });
  page.addEventListener("dragleave", (e) => {
    if (!page.contains(e.relatedTarget)) drop.classList.remove("is-over");
  });
  page.addEventListener("drop", async (e) => {
    e.preventDefault();
    drop.classList.remove("is-over");
    add(await collectDropped(e.dataTransfer));
  });

  const classPicker = radioGroup({
    ariaLabel: "Storage class",
    value: "STANDARD",
    items: STORAGE_CLASSES.map((c) => ({ value: c.value, label: c.label, description: c.description })),
  });
  const versioningNote = h("div");
  loadBucketInfo(bucket)
    .then((info) => {
      if (!info.versioning || info.versioning === "Suspended") {
        mount(versioningNote, alert({ type: "info" }, "Bucket Versioning is not enabled: uploading an object with the same name as an existing object replaces it. Enable Bucket Versioning on the Properties tab to keep previous versions."));
      } else {
        mount(versioningNote, alert({ type: "info" }, "Bucket Versioning is enabled: uploading an object with the same name keeps the previous object as a noncurrent version."));
      }
    })
    .catch(() => undefined);

  uploadBtn.addEventListener("click", () => startUpload(ctx, { bucket, prefix, crumbs, queue, storageClass: classPicker.value }));

  mount(
    page,
    pageHeader({ title: "Upload", description: "Add the files and folders you want to upload. Large files are sent in one request; for files of many gigabytes, use the AWS CLI or an SDK, which upload in parts." }),
    drop,
    container(
      {
        title: h("span", {}, "Files and folders", counter),
        description: "All files and folders in this table will be uploaded.",
        actions: [removeBtn, button({ label: "Add files", onClick: () => fileInput.click() }), button({ label: "Add folder", onClick: () => dirInput.click() })],
      },
      tbl.el,
      fileInput,
      dirInput,
    ),
    container({ title: "Destination" }, kvList([{ label: "Destination", value: s3Uri(bucket, prefix), copy: s3Uri(bucket, prefix) }], { columns: 1 }), versioningNote),
    container(
      { title: "Properties", description: "Specify the storage class and other properties for the uploaded objects." },
      expandable({ title: "Storage class", description: "Choose a storage class based on your use case and access requirements." }, classPicker),
    ),
    formActions(button({ label: "Cancel", variant: "link", href: bucketHref(bucket, { prefix }) }), uploadBtn),
  );
  setPage({ crumbs, title: "Upload", content: page });
  refresh();
}

function startUpload(ctx, { bucket, prefix, crumbs, queue, storageClass }) {
  const items = queue.map((q) => ({
    ...q,
    key: prefix + q.path,
    status: "pending",
    loaded: 0,
    error: "",
    statusEl: h("div", { class: "upload-status" }),
    abort: null,
  }));
  const total = items.reduce((n, q) => n + q.file.size, 0);
  const banner = h("div");
  const summary = h("div", { class: "summary" });
  const overall = h("div", { class: "progress", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100" }, h("div", { class: "progress__bar" }));
  let canceled = false;
  const cancelBtn = button({
    label: "Cancel remaining uploads",
    onClick: () => {
      canceled = true;
      for (const it of items) if (it.abort && it.status === "uploading") it.abort();
    },
  });
  const closeBtn = button({ label: "Close", variant: "primary", href: bucketHref(bucket, { prefix }), disabled: false });

  const drawStatus = (it) => {
    if (it.status === "uploading" || it.status === "pending") {
      const pct = it.file.size ? Math.floor((it.loaded / it.file.size) * 100) : 0;
      mount(
        it.statusEl,
        it.status === "pending" ? badge("pending", "Waiting") : h("div", { class: "progress progress--small" }, h("div", { class: "progress__bar", style: { width: `${pct}%` } })),
        it.status === "uploading" ? h("span", { class: "small muted" }, `${pct}%`) : null,
      );
    } else if (it.status === "done") mount(it.statusEl, badge("success", "Succeeded"));
    else mount(it.statusEl, badge("error", "Failed"), h("div", { class: "small error-text" }, it.error));
  };
  items.forEach(drawStatus);

  const tbl = table({
    ariaLabel: "Upload status",
    rowKey: (q) => String(q.id),
    pageSize: 50,
    filter: { placeholder: "Find by name", match: (q, t) => q.path.toLowerCase().includes(t) },
    columns: [
      { id: "name", header: "Name", cell: (q) => baseName(q.path) },
      { id: "folder", header: "Folder", cell: (q) => parentPrefix(q.path) || "-" },
      { id: "type", header: "Type", cell: (q) => q.file.type || fileType(q.path) },
      { id: "size", header: "Size", align: "right", cell: (q) => formatBytes(q.file.size) },
      { id: "status", header: "Status", cell: (q) => q.statusEl },
    ],
    rows: items,
  });

  const drawSummary = () => {
    const ok = items.filter((i) => i.status === "done");
    const bad = items.filter((i) => i.status === "failed");
    const sum = (list) => formatBytes(list.reduce((n, i) => n + i.file.size, 0));
    const sent = items.reduce((n, i) => n + (i.status === "done" ? i.file.size : i.loaded), 0);
    const pct = total ? Math.floor((sent / total) * 100) : 100;
    overall.firstChild.style.width = `${pct}%`;
    overall.setAttribute("aria-valuenow", String(pct));
    mount(
      summary,
      h("div", { class: "summary__item" }, h("div", { class: "summary__label" }, "Destination"), h("div", { class: "mono" }, s3Uri(bucket, prefix))),
      h("div", { class: "summary__item is-success" }, h("div", { class: "summary__label" }, "Succeeded"), h("div", {}, `${plural(ok.length, "file")}, ${sum(ok)}`)),
      h("div", { class: ["summary__item", bad.length ? "is-error" : ""] }, h("div", { class: "summary__label" }, "Failed"), h("div", {}, `${plural(bad.length, "file")}, ${sum(bad)}`)),
    );
  };

  mount(banner, alert({ type: "info", title: "Upload in progress" }, `Uploading ${plural(items.length, "file")} (${formatBytes(total)}). Keep this page open until the upload finishes.`, overall));
  drawSummary();

  setPage({
    crumbs,
    title: "Upload: status",
    content: h(
      "div",
      { class: "stack form-page" },
      pageHeader({ title: "Upload: status", description: "After you navigate away from this page, the following information is no longer available.", actions: [cancelBtn, closeBtn] }),
      banner,
      container({ title: "Summary" }, summary),
      container({ title: "Files and folders", counter: items.length }, tbl.el),
    ),
  });

  const leaveGuard = (e) => {
    e.preventDefault();
    e.returnValue = "";
  };
  window.addEventListener("beforeunload", leaveGuard);

  let index = 0;
  let lastDraw = 0;
  const worker = async () => {
    while (index < items.length) {
      const it = items[index];
      index += 1;
      if (canceled) {
        it.status = "failed";
        it.error = "Canceled";
        drawStatus(it);
        continue;
      }
      it.status = "uploading";
      drawStatus(it);
      const job = uploadFile({
        bucket,
        key: it.key,
        file: it.file,
        storageClass,
        onProgress: (loaded) => {
          it.loaded = loaded;
          const now = Date.now();
          if (now - lastDraw > 150) {
            lastDraw = now;
            drawStatus(it);
            drawSummary();
          }
        },
      });
      it.abort = job.abort;
      try {
        await job.promise;
        it.status = "done";
        it.loaded = it.file.size;
      } catch (e) {
        it.status = "failed";
        it.error = errorText(e);
      }
      drawStatus(it);
      drawSummary();
    }
  };
  Promise.all([worker(), worker(), worker()]).then(() => {
    window.removeEventListener("beforeunload", leaveGuard);
    cancelBtn.remove();
    const bad = items.filter((i) => i.status === "failed").length;
    const ok = items.length - bad;
    refreshBuckets().catch(() => undefined);
    mount(
      banner,
      bad
        ? alert({ type: "error", title: "Upload failed" }, `${plural(bad, "file")} could not be uploaded${ok ? `; ${plural(ok, "file")} succeeded` : ""}. See the Status column for details.`)
        : alert({ type: "success", title: "Upload succeeded" }, `${plural(ok, "file")} (${formatBytes(total)}) uploaded to ${s3Uri(bucket, prefix)}.`),
    );
    void ctx;
  });
}
