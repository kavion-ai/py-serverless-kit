// The object page: header actions, tabs Properties | Permissions | Versions.

import { h, mount } from "../core/dom.js";
import { state } from "../core/state.js";
import { api, presign, downloadUrl, errorText } from "../core/api.js";
import { navigate } from "../core/router.js";
import { baseName, parentPrefix, formatBytes, formatDate, fileType, storageClassLabel, STORAGE_CLASSES, ARCHIVED_CLASSES } from "../core/format.js";
import { s3Uri, objectArn, objectUrl } from "../core/s3.js";
import { tabs } from "../components/tabs.js";
import { table } from "../components/table.js";
import { button, link } from "../components/button.js";
import { container, loading, emptyState } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { kvList } from "../components/kv-list.js";
import { dropdown } from "../components/dropdown.js";
import { alert } from "../components/alert.js";
import { badge, pill } from "../components/badge.js";
import { copyButton } from "../components/copy-button.js";
import { modal, confirmModal } from "../components/modal.js";
import { field, input, radioGroup, checkbox } from "../components/field.js";
import { flash } from "../components/toast.js";
import { setPage } from "./shell.js";
import { bucketCrumbs, bucketHref, bucketPath, objectHref, objectEditHref, loadBucketInfo, showLoadError, onOff } from "./common.js";
import { runOpen, runDownload, shareModal, copyMoveModal, renameModal, restoreModal } from "./object-actions.js";

const TABS = [
  { id: "properties", label: "Properties" },
  { id: "permissions", label: "Permissions" },
  { id: "versions", label: "Versions" },
];

const TEXT_TYPES = /^(text\/|application\/(json|xml|javascript|x-javascript|x-yaml|yaml|x-sh|toml|x-ndjson)|image\/svg\+xml)/;
const TEXT_EXT = /\.(txt|md|csv|tsv|json|xml|ya?ml|log|ini|conf|cfg|toml|js|mjs|ts|py|sh|html?|css|sql)$/i;

export async function render(ctx) {
  const bucket = ctx.params.bucket;
  const key = ctx.query.key || "";
  const versionParam = ctx.query.versionId || "";
  const tab = TABS.some((t) => t.id === ctx.query.tab) ? ctx.query.tab : "properties";
  if (!key) {
    navigate(bucketPath(bucket), {}, { replace: true });
    return;
  }
  const crumbs = bucketCrumbs(bucket, parentPrefix(key), { label: baseName(key) });
  setPage({ crumbs, title: baseName(key), content: loading() });
  let o;
  let info;
  try {
    [o, info] = await Promise.all([api("HeadObject", { bucket, key, versionId: versionParam }), loadBucketInfo(bucket)]);
  } catch (e) {
    if (ctx.alive()) showLoadError(e, crumbs, e.code === "NoSuchKey" ? "The object does not exist" : "The object could not be loaded");
    return;
  }
  if (!ctx.alive()) return;

  const vid = o.latest ? "" : o.versionId;
  const reloadPage = () => navigate(bucketPath(bucket, "/object"), { key, versionId: versionParam, tab }, { replace: true });
  const toFolder = () => navigate(bucketPath(bucket), { prefix: parentPrefix(key) });
  const archived = ARCHIVED_CLASSES.includes(o.class);

  const objectActions = dropdown({
    label: "Object actions",
    items: () => [
      { label: "Share with a presigned URL", onClick: () => shareModal({ bucket, key, versionId: vid }) },
      { divider: true },
      { label: "Copy", disabled: !o.latest, onClick: () => copyMoveModal({ bucket, prefix: parentPrefix(key), items: [{ key }], move: false, onDone: reloadPage }) },
      { label: "Move", disabled: !o.latest, onClick: () => copyMoveModal({ bucket, prefix: parentPrefix(key), items: [{ key }], move: true, onDone: toFolder }) },
      { label: "Rename object", disabled: !o.latest, onClick: () => renameModal({ bucket, key, onDone: (newKey) => navigate(bucketPath(bucket, "/object"), { key: newKey }) }) },
      { divider: true },
      { label: "Edit storage class", disabled: !o.latest, onClick: () => navigate(bucketPath(bucket, "/object/edit/storage-class"), { key }) },
      { label: "Edit metadata", disabled: !o.latest, onClick: () => navigate(bucketPath(bucket, "/object/edit/metadata"), { key }) },
      { label: "Edit tags", onClick: () => navigate(bucketPath(bucket, "/object/edit/tags"), { key, versionId: vid }) },
      archived ? { label: "Initiate restore", onClick: () => restoreModal({ bucket, key, versionId: vid, onDone: reloadPage }) } : null,
      { divider: true },
      {
        label: o.latest ? "Delete" : "Delete this version",
        onClick: () => {
          state.pendingDelete = { bucket, prefix: parentPrefix(key), versions: !o.latest, items: [{ key, versionId: o.latest ? "" : o.versionId, folder: false, size: o.size }] };
          navigate(bucketPath(bucket, "/delete-objects"), { prefix: parentPrefix(key) });
        },
      },
    ],
  });

  const notices = [];
  if (!o.latest) {
    const top = o.versions && o.versions[0];
    notices.push(
      top && top.deleteMarker
        ? alert({ type: "warning", title: "This object is deleted" }, "The current version is a delete marker, so the object is hidden from listings and requests without a version ID. To restore it, make this version current on the Versions tab, or delete the delete marker.")
        : alert({ type: "info", title: "You are viewing a previous version of this object" }, "Previous versions are kept because Bucket Versioning is on. ", link("View the current version", objectHref(bucket, key))),
    );
  }

  const body = h("div", { class: "tab-body" });
  setPage({
    crumbs,
    title: baseName(key),
    content: h(
      "div",
      { class: "stack" },
      pageHeader({
        title: baseName(key),
        extra: o.latest ? null : h("div", { class: "page-header__meta" }, h("span", { class: "mono small" }, `Version ID ${o.versionId}`)),
        actions: [
          copyButton(s3Uri(bucket, key), { label: "Copy S3 URI", done: "S3 URI copied" }),
          button({ label: "Download", icon: "download", onClick: () => runDownload(bucket, key, vid) }),
          button({ label: "Open", icon: "external", onClick: () => runOpen(bucket, key, vid) }),
          objectActions,
        ],
      }),
      notices,
      tabs({ tabs: TABS, active: tab, ariaLabel: "Object", onChange: (id) => navigate(bucketPath(bucket, "/object"), { key, versionId: versionParam, tab: id === "properties" ? "" : id }) }),
      body,
    ),
  });

  const args = { ctx, bucket, key, o, info, vid, body, reloadPage };
  if (tab === "properties") propertiesTab(args);
  else if (tab === "permissions") permissionsTab(args);
  else versionsTab(args);
}

// ----------------------------------------------------------------------------- Properties

function propertiesTab({ bucket, key, o, info, vid, body, reloadPage }) {
  const url = objectUrl(bucket, key) + (vid ? `?versionId=${encodeURIComponent(vid)}` : "");
  const overview = container(
    { title: "Object overview" },
    kvList([
      { label: "Owner", value: info.account },
      { label: "AWS Region", value: info.region },
      { label: "Last modified", value: formatDate(o.modified) },
      { label: "Size", value: `${formatBytes(o.size)} (${Number(o.size).toLocaleString()} bytes)` },
      { label: "Type", value: fileType(key) },
      { label: "Key", value: key, copy: key, mono: true },
      { label: "S3 URI", value: s3Uri(bucket, key), copy: s3Uri(bucket, key), mono: true },
      { label: "Amazon Resource Name (ARN)", value: objectArn(bucket, key), copy: objectArn(bucket, key), mono: true },
      { label: "Entity tag (Etag)", value: o.etag + (o.parts ? ` (${o.parts} parts)` : ""), copy: o.etag, mono: true },
      { label: "Object URL", value: link(url, url, { external: true }), copy: url },
      o.versionId && o.versionId !== "null" ? { label: "Version ID", value: o.versionId, copy: o.versionId, mono: true } : null,
      { label: "Content type", value: o.type || "-" },
      o.checksum ? { label: `Checksum (${o.checksum.alg})`, value: o.checksum.value, copy: o.checksum.value, mono: true } : null,
      o.redirect ? { label: "Website redirect location", value: o.redirect, mono: true } : null,
    ]),
  );

  const preview = previewContainer(bucket, key, o, vid);

  const archived = ARCHIVED_CLASSES.includes(o.class);
  const storage = container(
    {
      title: "Storage class",
      description: "Storage classes are designed for different use cases and access patterns.",
      actions: o.latest ? [button({ label: "Edit", href: objectEditHref(bucket, "storage-class", key) })] : [],
    },
    kvList(
      [
        { label: "Storage class", value: storageClassLabel(o.class) },
        { label: "Description", value: (STORAGE_CLASSES.find((c) => c.value === o.class) || {}).description || "-" },
        archived ? { label: "Restoration status", value: o.restore ? `Restored until ${formatDate(o.restore)}` : "Not restored" } : null,
      ],
      { columns: archived ? 3 : 2 },
    ),
    archived && !o.restore ? h("div", { class: "btn-row" }, button({ label: "Initiate restore", onClick: () => restoreModal({ bucket, key, versionId: vid, onDone: reloadPage }) })) : null,
  );

  const tagRows = Object.entries(o.tags || {}).map(([k, v]) => ({ k, v }));
  const tagsTbl = table({
    ariaLabel: "Tags",
    rowKey: (r) => r.k,
    pageSize: 0,
    columns: [
      { id: "k", header: "Key", cell: (r) => r.k },
      { id: "v", header: "Value", cell: (r) => r.v || "-" },
    ],
    rows: tagRows,
    empty: emptyState({ title: "No tags", text: "No tags associated with this resource." }),
  });
  const tagsBox = container(
    {
      title: "Tags",
      counter: tagRows.length,
      description: "You can use object tags to analyze, manage, and specify permissions for objects, and to filter lifecycle rules.",
      actions: [button({ label: "Edit", href: objectEditHref(bucket, "tags", key, vid) })],
    },
    tagsTbl.el,
  );

  const metaRows = [{ type: "System defined", k: "Content-Type", v: o.type || "binary/octet-stream" }];
  for (const [k, v] of Object.entries(o.headers || {})) metaRows.push({ type: "System defined", k: k.replace(/(^|-)([a-z])/g, (m, a, b) => a + b.toUpperCase()), v });
  for (const [k, v] of Object.entries(o.meta || {})) metaRows.push({ type: "User defined", k: `x-amz-meta-${k}`, v });
  const metaTbl = table({
    ariaLabel: "Metadata",
    rowKey: (r) => r.k,
    pageSize: 0,
    columns: [
      { id: "type", header: "Type", cell: (r) => r.type },
      { id: "k", header: "Key", cell: (r) => h("span", { class: "mono" }, r.k) },
      { id: "v", header: "Value", cell: (r) => h("span", { class: "mono break" }, r.v) },
    ],
    rows: metaRows,
  });
  const metaBox = container(
    {
      title: "Metadata",
      counter: metaRows.length,
      description: "Metadata is optional information provided as a name-value (key-value) pair.",
      actions: o.latest ? [button({ label: "Edit", href: objectEditHref(bucket, "metadata", key) })] : [],
    },
    metaTbl.el,
  );

  const parts = [overview, preview, storage, tagsBox, metaBox];
  if (info.objectLock) {
    parts.push(
      container(
        {
          title: "Object Lock retention",
          description: "Prevents this object version from being deleted or overwritten until the retain-until date.",
          actions: [button({ label: "Edit", onClick: () => retentionModal({ bucket, key, o, vid, reloadPage }) })],
        },
        kvList(
          [
            { label: "Retention", value: onOff(Boolean(o.retention)) },
            { label: "Retention mode", value: o.retention ? (o.retention.mode === "COMPLIANCE" ? "Compliance" : "Governance") : "-" },
            { label: "Retain until date", value: o.retention ? formatDate(o.retention.until) : "-" },
          ],
        ),
      ),
      container(
        {
          title: "Object Lock legal hold",
          description: "Prevents this object version from being deleted until the legal hold is removed. A legal hold has no expiration date.",
          actions: [button({ label: "Edit", onClick: () => legalHoldModal({ bucket, key, o, vid, reloadPage }) })],
        },
        kvList([{ label: "Legal hold", value: onOff(o.legalHold) }], { columns: 1 }),
      ),
    );
  }
  body.replaceChildren(h("div", { class: "stack" }, parts.filter(Boolean)));
}

function previewContainer(bucket, key, o, vid) {
  const type = o.type || "";
  const isImage = /^image\/(png|jpe?g|gif|webp|bmp|avif|x-icon|vnd\.microsoft\.icon)$/.test(type);
  const isVideo = /^video\//.test(type);
  const isAudio = /^audio\//.test(type);
  const isText = (TEXT_TYPES.test(type) || TEXT_EXT.test(key)) && Number(o.size) <= 256 * 1024 && !isImage;
  if (!(isImage || isVideo || isAudio || isText) || Number(o.size) === 0) return null;
  const box = h("div", { class: "preview" }, loading("Loading preview"));
  (async () => {
    try {
      if (isText) {
        const res = await fetch(downloadUrl(bucket, key, vid), { credentials: "same-origin" });
        if (!res.ok) throw new Error(`The preview could not be loaded (${res.status}).`);
        const text = await res.text();
        mount(box, h("pre", { class: "preview__text" }, text.slice(0, 50000)), text.length > 50000 ? h("div", { class: "muted small" }, "Only the first 50,000 characters are shown.") : null);
        return;
      }
      const { url } = await presign({ bucket, key, versionId: vid, expires: 300, disposition: "inline" });
      if (isImage) mount(box, h("img", { class: "preview__media", src: url, alt: `Preview of ${baseName(key)}` }));
      else mount(box, h(isVideo ? "video" : "audio", { class: "preview__media", src: url, controls: true, preload: "metadata" }));
    } catch (e) {
      mount(box, alert({ type: "warning" }, errorText(e)));
    }
  })();
  return container({ title: "Preview" }, box);
}

function retentionModal({ bucket, key, o, vid, reloadPage }) {
  const current = o.retention;
  const mode = radioGroup({
    ariaLabel: "Retention mode",
    value: current ? current.mode : "",
    items: [
      { value: "", label: "Disable", description: "No retention period (only possible when the current retention can be removed)." },
      { value: "GOVERNANCE", label: "Governance mode", description: "Users with the bypass option can overwrite or delete the version or alter its lock settings." },
      { value: "COMPLIANCE", label: "Compliance mode", description: "No user can overwrite or delete the version, or shorten the retention, until the retain-until date." },
    ],
  });
  const pad = (n) => String(n).padStart(2, "0");
  const toLocal = (iso) => {
    const d = new Date(iso);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };
  const until = input({ type: "datetime-local", value: current ? toLocal(current.until) : toLocal(new Date(Date.now() + 30 * 86400000).toISOString()) });
  const untilField = field({ label: "Retain until date", control: until, description: "In your local time zone." });
  const bypass = checkbox({ label: "Bypass governance retention", description: "Needed to shorten or remove a governance-mode retention." });
  modal({
    title: "Edit Object Lock retention",
    body: [mode, untilField, bypass],
    actions: [
      {
        label: "Save changes",
        onClick: async () => {
          const m = mode.value;
          let iso = "";
          if (m) {
            const d = new Date(until.value);
            if (!until.value || Number.isNaN(d.getTime()) || d.getTime() <= Date.now()) {
              untilField.setError("Choose a date in the future.");
              return false;
            }
            iso = d.toISOString().replace(/\.\d{3}Z$/, "Z");
          }
          await api("ObjectLock", { bucket, key, versionId: vid, mode: m, until: iso, bypass: bypass.input.checked });
          flash("success", "", { title: "Successfully edited Object Lock retention" });
          reloadPage();
          return undefined;
        },
      },
    ],
  });
}

function legalHoldModal({ bucket, key, o, vid, reloadPage }) {
  const hold = radioGroup({
    ariaLabel: "Legal hold",
    value: o.legalHold ? "on" : "off",
    items: [
      { value: "off", label: "Disable" },
      { value: "on", label: "Enable", description: "The version cannot be deleted until the legal hold is removed." },
    ],
  });
  modal({
    title: "Edit Object Lock legal hold",
    body: [hold],
    actions: [
      {
        label: "Save changes",
        onClick: async () => {
          await api("ObjectLock", { bucket, key, versionId: vid, legalHold: hold.value === "on" });
          flash("success", "", { title: "Successfully edited Object Lock legal hold" });
          reloadPage();
          return undefined;
        },
      },
    ],
  });
}

// ----------------------------------------------------------------------------- Permissions

function aclRows(canned) {
  return [
    { grantee: "Object owner (your account)", object: "Read", acl: "Read, Write" },
    { grantee: "Everyone (public access)", object: canned === "public-read" || canned === "public-read-write" ? "Read" : "-", acl: "-" },
    { grantee: "Authenticated users group (anyone with an access key)", object: canned === "authenticated-read" ? "Read" : "-", acl: "-" },
    canned === "bucket-owner-read" || canned === "bucket-owner-full-control" ? { grantee: "Bucket owner", object: "Read", acl: canned === "bucket-owner-full-control" ? "Read, Write" : "-" } : null,
  ].filter(Boolean);
}

function permissionsTab({ bucket, key, o, info, vid, body, reloadPage }) {
  if (info.ownership === "BucketOwnerEnforced") {
    body.replaceChildren(
      container(
        { title: "Access control list (ACL)" },
        alert(
          { type: "info", title: "This bucket has the bucket owner enforced setting applied for Object Ownership" },
          "When bucket owner enforced is applied, use bucket policies to control access. ",
          link("Go to the bucket's permissions", bucketHref(bucket, { tab: "permissions" })),
        ),
      ),
    );
    return;
  }
  const tbl = table({
    ariaLabel: "Access control list",
    rowKey: (r) => r.grantee,
    pageSize: 0,
    columns: [
      { id: "g", header: "Grantee", cell: (r) => r.grantee },
      { id: "o", header: "Object", cell: (r) => r.object },
      { id: "a", header: "Object ACL", cell: (r) => r.acl },
    ],
    rows: aclRows(o.acl),
  });
  body.replaceChildren(
    container(
      {
        title: "Access control list (ACL)",
        description: "Grant basic read permissions to other accounts or to everyone.",
        actions: [button({ label: "Edit", onClick: () => objectAclModal({ bucket, key, o, info, vid, reloadPage }) })],
      },
      tbl.el,
      h("p", { class: "muted small" }, "Canned ACL: ", h("span", { class: "mono" }, o.acl || "private")),
    ),
  );
}

function objectAclModal({ bucket, key, o, info, vid, reloadPage }) {
  const everyone = checkbox({ label: "Everyone (public access): Object Read", checked: o.acl === "public-read" || o.acl === "public-read-write" });
  const authed = checkbox({ label: "Authenticated users group: Object Read", description: "Anyone with an access key for this server.", checked: o.acl === "authenticated-read" });
  const ack = checkbox({ label: "I understand the effects of these changes on this object." });
  const warning = alert({ type: "warning", title: "Granting public access" }, "Everyone will be able to download this object without keys.", h("div", { class: "alert__ack" }, ack));
  const blocked = info.publicBlock.BlockPublicAcls;
  const sync = () => {
    warning.hidden = !everyone.input.checked;
    authed.input.disabled = everyone.input.checked;
  };
  everyone.input.addEventListener("change", sync);
  sync();
  modal({
    title: "Edit access control list (ACL)",
    body: [
      blocked ? alert({ type: "warning" }, "Block public access (BlockPublicAcls) is on for this bucket: public ACLs are refused.") : null,
      everyone,
      authed,
      warning,
    ],
    actions: [
      {
        label: "Save changes",
        onClick: async () => {
          if (everyone.input.checked && !ack.input.checked) throw new Error("Acknowledge the effects of granting public access.");
          const acl = everyone.input.checked ? "public-read" : authed.input.checked ? "authenticated-read" : "private";
          await api("PutObjectAcl", { bucket, key, versionId: vid, acl });
          flash("success", "", { title: "Successfully edited the access control list" });
          reloadPage();
          return undefined;
        },
      },
    ],
  });
}

// ----------------------------------------------------------------------------- Versions

function versionsTab({ bucket, key, o, info, body }) {
  let selected = null;
  const isCurrentView = (v) => v.versionId === o.versionId;
  const makeCurrent = button({ label: "Make current", disabled: true });
  const download = button({ label: "Download", icon: "download", disabled: true });
  const del = button({ label: "Delete", disabled: true });
  const tbl = table({
    ariaLabel: "Versions",
    selectable: "single",
    rowKey: (v) => v.versionId,
    pageSize: 50,
    rowClass: (v) => (isCurrentView(v) ? "is-viewing" : ""),
    onSelect: (rows) => {
      selected = rows[0] || null;
      makeCurrent.disabled = !selected || selected.latest || selected.deleteMarker;
      download.disabled = !selected || selected.deleteMarker;
      del.disabled = !selected;
    },
    columns: [
      {
        id: "id",
        header: "Version ID",
        cell: (v) =>
          h(
            "span",
            { class: "mono small" },
            v.deleteMarker ? v.versionId : link(v.versionId, objectHref(bucket, key, v.latest ? "" : v.versionId)),
            v.latest ? pill("Current version", "info") : null,
            isCurrentView(v) ? pill("Viewing", "neutral") : null,
          ),
      },
      { id: "type", header: "Type", cell: (v) => (v.deleteMarker ? badge("stopped", "Delete marker") : fileType(key)) },
      { id: "modified", header: "Last modified", cell: (v) => formatDate(v.modified) },
      { id: "size", header: "Size", align: "right", cell: (v) => (v.deleteMarker ? "-" : formatBytes(v.size)) },
      { id: "class", header: "Storage class", cell: (v) => (v.deleteMarker ? "-" : storageClassLabel(v.class)) },
    ],
    rows: o.versions || [],
  });
  makeCurrent.addEventListener("click", async () => {
    try {
      await api("RestoreVersion", { bucket, key, versionId: selected.versionId });
      flash("success", "The version was copied on top as the new current version.", { title: "Successfully made the version current" });
      navigate(bucketPath(bucket, "/object"), { key, tab: "versions" });
    } catch (e) {
      flash("error", errorText(e), { title: "Could not make the version current" });
    }
  });
  download.addEventListener("click", () => runDownload(bucket, key, selected.latest ? "" : selected.versionId));
  del.addEventListener("click", async () => {
    const v = selected;
    const ok = await confirmModal({
      title: v.deleteMarker ? "Delete delete marker" : "Delete version",
      message: v.deleteMarker
        ? "Deleting this delete marker makes the previous version of the object current again."
        : "Permanently deleting this version cannot be undone. The object's other versions are kept.",
      confirmLabel: "Delete",
      variant: "danger",
      typed: "permanently delete",
    });
    if (!ok) return;
    try {
      const out = await api("DeleteObjects", { bucket, objects: [{ key, versionId: v.versionId }] });
      if (out.errors && out.errors.length) throw new Error(`${out.errors[0].message} (${out.errors[0].code})`);
      flash("success", "", { title: `Successfully deleted version ${v.versionId}` });
      const remaining = (o.versions || []).filter((x) => x.versionId !== v.versionId && !x.deleteMarker);
      if (!remaining.length) navigate(bucketPath(bucket), { prefix: parentPrefix(key) });
      else navigate(bucketPath(bucket, "/object"), { key, tab: "versions" });
    } catch (e) {
      flash("error", errorText(e), { title: "Could not delete the version" });
    }
  });
  body.replaceChildren(
    h(
      "div",
      { class: "stack" },
      !info.versioning ? alert({ type: "info" }, "Bucket Versioning is not enabled for this bucket, so the object has a single version. ", link("Enable Bucket Versioning", bucketHref(bucket, { tab: "properties" }))) : null,
      container(
        { title: "Versions", counter: (o.versions || []).length, description: "Every version of this object, newest first.", actions: [makeCurrent, download, del] },
        tbl.el,
      ),
    ),
  );
}
