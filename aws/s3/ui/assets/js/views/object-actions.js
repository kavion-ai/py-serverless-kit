// Object actions shared by the Objects tab and the object page: Open, Download, Share (presigned URL), Copy, Move,
// Rename, Calculate total size, Initiate restore, Create folder.

import { h, mount } from "../core/dom.js";
import { state } from "../core/state.js";
import { api, presign, openObject, downloadObject, errorText } from "../core/api.js";
import { baseName, formatBytes, durationText, plural } from "../core/format.js";
import { s3Uri } from "../core/s3.js";
import { modal } from "../components/modal.js";
import { field, input, select } from "../components/field.js";
import { alert } from "../components/alert.js";
import { kvList } from "../components/kv-list.js";
import { copyButton } from "../components/copy-button.js";
import { loading } from "../components/container.js";
import { flash } from "../components/toast.js";
import { refreshBuckets } from "./shell.js";

export async function runOpen(bucket, key, versionId) {
  try {
    await openObject(bucket, key, versionId);
  } catch (e) {
    flash("error", errorText(e), { title: `Could not open ${baseName(key)}` });
  }
}

export async function runDownload(bucket, key, versionId) {
  try {
    await downloadObject(bucket, key, versionId);
  } catch (e) {
    flash("error", errorText(e), { title: `Could not download ${baseName(key)}` });
  }
}

const UNITS = [
  { value: "1", label: "Seconds" },
  { value: "60", label: "Minutes" },
  { value: "3600", label: "Hours" },
  { value: "86400", label: "Days" },
];
const MAX = 604800;

/** Share with a presigned URL. */
export function shareModal({ bucket, key, versionId }) {
  const amount = input({ type: "number", min: "1", step: "1", value: "60", "aria-label": "Time interval" });
  const unit = select({ options: UNITS, value: "60", ariaLabel: "Unit" });
  const result = h("div", { class: "share__result" });
  const amountField = field({
    label: "Time interval until the presigned URL expires",
    control: h("div", { class: "field-row" }, h("div", { class: "grow" }, amount), unit),
    constraint: "Between 1 second and 7 days.",
  });
  const m = modal({
    title: "Share with a presigned URL",
    size: "medium",
    cancelLabel: "Close",
    body: [
      alert({ type: "info" }, "Anyone with the presigned URL can download the object until the URL expires, even when the bucket is private. The URL is signed with your access key; a bucket policy that denies the request still applies."),
      h("p", { class: "muted mono break" }, s3Uri(bucket, key)),
      amountField,
      result,
    ],
    actions: [
      {
        label: "Create presigned URL",
        onClick: async () => {
          const seconds = Math.round(Number(amount.value) * Number(unit.value));
          if (!Number.isFinite(seconds) || seconds < 1 || seconds > MAX) {
            amountField.setError("Enter a time interval between 1 second and 7 days.");
            return false;
          }
          amountField.setError("");
          const data = await presign({ bucket, key, versionId, method: "GET", expires: seconds });
          const until = new Date(Date.now() + data.expires * 1000);
          const urlBox = h("textarea", { class: "input textarea mono", readonly: true, rows: 4, "aria-label": "Presigned URL" });
          urlBox.value = data.url;
          mount(
            result,
            alert({ type: "success", title: "Presigned URL created" }, `The URL expires ${until.toLocaleString()} (in ${durationText(data.expires)}).`),
            urlBox,
            h("div", { class: "btn-row" }, copyButton(data.url, { label: "Copy presigned URL", done: "Presigned URL copied" })),
          );
          urlBox.select();
          return false;
        },
      },
    ],
  });
  return m;
}

/** Copy or move objects and folders to another bucket / folder. items: [{key, folder}] */
export function copyMoveModal({ bucket, prefix, items, move, onDone }) {
  const buckets = (state.buckets || []).map((b) => b.name);
  if (!buckets.includes(bucket)) buckets.unshift(bucket);
  const dest = select({ options: buckets, value: bucket, ariaLabel: "Destination bucket" });
  const folder = input({ value: prefix, placeholder: "folder/ (empty for the bucket root)" });
  const folderField = field({ label: "Destination folder", control: folder, constraint: "Objects keep their names; folders are copied with everything inside." });
  const list = h("ul", { class: "plain-list mono small" }, items.slice(0, 8).map((i) => h("li", {}, baseName(i.key) + (i.folder ? "/" : ""))), items.length > 8 ? h("li", {}, `and ${items.length - 8} more`) : null);
  modal({
    title: move ? "Move objects" : "Copy objects",
    body: [
      h("p", {}, `${move ? "Move" : "Copy"} ${plural(items.length, "item")}:`),
      list,
      field({ label: "Destination bucket", control: dest }),
      folderField,
      move ? alert({ type: "info" }, "Moving copies the objects to the destination and then deletes them from the source (a delete marker when versioning is on).") : null,
    ],
    actions: [
      {
        label: move ? "Move" : "Copy",
        onClick: async () => {
          let target = folder.value.trim().replace(/^\/+/, "");
          if (target && !target.endsWith("/")) target += "/";
          if (dest.value === bucket && target === prefix) {
            folderField.setError("Choose a different destination than the source folder.");
            return false;
          }
          folderField.setError("");
          let done = 0;
          for (const item of items) {
            const toKey = target + baseName(item.key) + (item.folder ? "/" : "");
            await api("Copy", { bucket, key: item.key, toBucket: dest.value, toKey, move: Boolean(move) });
            done += 1;
          }
          refreshBuckets().catch(() => undefined);
          flash("success", `${s3Uri(dest.value, target)}`, { title: `Successfully ${move ? "moved" : "copied"} ${plural(done, "item")}` });
          if (onDone) onDone();
        },
      },
    ],
  });
}

/** Rename one object (copy to the new key in the same folder, then delete the old one). */
export function renameModal({ bucket, key, onDone }) {
  const folderPart = key.slice(0, key.length - baseName(key).length);
  const name = input({ value: baseName(key) });
  const nameField = field({ label: "New object name", control: name, constraint: `The object stays in ${folderPart || "the bucket root"}.` });
  modal({
    title: "Rename object",
    body: [alert({ type: "info" }, "Renaming copies the object to the new name and deletes the original (a delete marker when versioning is on). Tags, metadata and the storage class are kept."), nameField],
    actions: [
      {
        label: "Save changes",
        onClick: async () => {
          const v = name.value.trim();
          if (!v || v.includes("/")) {
            nameField.setError(v ? "The name cannot contain a slash (/)." : "Enter a name.");
            return false;
          }
          if (v === baseName(key)) return undefined;
          await api("Copy", { bucket, key, toBucket: bucket, toKey: folderPart + v, move: true });
          flash("success", "", { title: `Successfully renamed "${baseName(key)}" to "${v}"` });
          if (onDone) onDone(folderPart + v);
          return undefined;
        },
      },
    ],
  });
}

async function folderTotals(bucket, prefix) {
  let objects = 0;
  let bytes = 0;
  let token = "";
  for (let i = 0; i < 10000; i += 1) {
    const data = await api("ListObjects", { bucket, prefix, delimiter: "", token, max: 1000 });
    for (const o of data.objects || []) {
      objects += 1;
      bytes += Number(o.size) || 0;
    }
    if (!data.next) break;
    token = data.next;
  }
  return { objects, bytes };
}

/** Calculate total size of the selected objects and folders. items: [{key, folder, size}] */
export function totalSizeModal({ bucket, items }) {
  const body = h("div", {}, loading("Calculating"));
  modal({ title: "Calculate total size", body, actions: [], cancelLabel: "Close" });
  (async () => {
    let objects = 0;
    let bytes = 0;
    for (const item of items) {
      if (item.folder) {
        const t = await folderTotals(bucket, item.key);
        objects += t.objects;
        bytes += t.bytes;
      } else {
        objects += 1;
        bytes += Number(item.size) || 0;
      }
    }
    mount(
      body,
      kvList(
        [
          { label: "Total number of objects", value: objects.toLocaleString() },
          { label: "Total size", value: `${formatBytes(bytes)} (${bytes.toLocaleString()} bytes)` },
        ],
        { columns: 2 },
      ),
      h("p", { class: "muted small" }, "Folders are counted with everything inside them (current versions only)."),
    );
  })().catch((e) => mount(body, alert({ type: "error" }, errorText(e))));
}

/** Initiate restore of an archived (Glacier Flexible Retrieval / Deep Archive) object. */
export function restoreModal({ bucket, key, versionId, onDone }) {
  const days = input({ type: "number", min: "1", max: "365", value: "7" });
  const daysField = field({ label: "Number of days that the restored copy is available", control: days, constraint: "Between 1 and 365 days." });
  modal({
    title: "Initiate restore",
    body: [h("p", {}, "Archived objects must be restored before they can be downloaded. The restored copy is kept for the number of days you choose."), daysField],
    actions: [
      {
        label: "Initiate restore",
        onClick: async () => {
          const n = Number(days.value);
          if (!Number.isInteger(n) || n < 1 || n > 365) {
            daysField.setError("Enter a whole number between 1 and 365.");
            return false;
          }
          await api("RestoreArchived", { bucket, key, versionId: versionId || "", days: n });
          flash("success", "", { title: `Restored "${baseName(key)}" for ${plural(n, "day")}` });
          if (onDone) onDone();
          return undefined;
        },
      },
    ],
  });
}

/** Create folder (an empty object whose key ends with "/"). */
export function createFolderModal({ bucket, prefix, onDone }) {
  const name = input({ placeholder: "folder-name" });
  const nameField = field({
    label: "Folder name",
    control: name,
    constraint: 'Folder names can\'t contain "/". The folder is an empty object whose key ends with "/".',
  });
  modal({
    title: "Create folder",
    body: [h("p", { class: "muted" }, `Destination: ${s3Uri(bucket, prefix)}`), nameField],
    actions: [
      {
        label: "Create folder",
        onClick: async () => {
          const v = name.value.trim();
          if (!v || v.includes("/")) {
            nameField.setError(v ? 'Folder names can\'t contain "/".' : "Enter a folder name.");
            return false;
          }
          await api("CreateFolder", { bucket, key: `${prefix}${v}/` });
          flash("success", "", { title: `Successfully created folder "${v}"` });
          if (onDone) onDone();
          return undefined;
        },
      },
    ],
  });
  name.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const btn = name.closest("dialog").querySelector(".modal__footer .btn--primary");
      if (btn) btn.click();
    }
  });
}
