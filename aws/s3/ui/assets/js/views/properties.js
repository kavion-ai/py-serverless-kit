// The bucket's Properties tab: overview, Bucket Versioning, Tags, Object Lock, Static website hosting.

import { h } from "../core/dom.js";
import { formatDate } from "../core/format.js";
import { objectLockOf, websiteFromXml } from "../core/s3.js";
import { container, emptyState } from "../components/container.js";
import { kvList } from "../components/kv-list.js";
import { table } from "../components/table.js";
import { link } from "../components/button.js";
import { copyButton } from "../components/copy-button.js";
import { onOff, editButton, editHref } from "./common.js";

/** The website endpoint URLs: the path-style one on this origin and the virtual-host names. */
export function websiteEndpoints(info) {
  const main = location.origin + (info.websiteUrl || `/-/website/${info.name}/`);
  const port = location.port ? `:${location.port}` : "";
  const hosts = (info.websiteHosts || []).map((host) => `${location.protocol}//${host}${port}/`);
  return { main, hosts };
}

export function renderPropertiesTab({ bucket, info, body }) {
  const versioning = info.versioning || "";
  const lock = objectLockOf(info);
  const site = websiteFromXml(info.configs.website);
  const tagRows = Object.entries(info.tags).map(([k, v]) => ({ k, v }));
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

  const { main, hosts } = websiteEndpoints(info);
  const endpoints = h(
    "div",
    { class: "stack-xs" },
    h("div", { class: "copyable" }, copyButton(main, { title: "Copy website endpoint" }), link(main, main, { external: true })),
    hosts.map((u) => h("div", { class: "copyable small" }, copyButton(u, { title: "Copy website endpoint" }), link(u, u, { external: true }))),
  );

  body.replaceChildren(
    h(
      "div",
      { class: "stack" },
      container(
        { title: "Bucket overview" },
        kvList([
          { label: "AWS Region", value: info.region },
          { label: "Amazon Resource Name (ARN)", value: info.arn, copy: info.arn, mono: true },
          { label: "Creation date", value: formatDate(info.created) },
        ]),
      ),
      container(
        {
          title: "Bucket Versioning",
          description: "Versioning is a means of keeping multiple variants of an object in the same bucket. You can use versioning to preserve, retrieve, and restore every version of every object stored in your bucket. With versioning, you can recover from both unintended user actions and application failures.",
          actions: [editButton(editHref(bucket, "versioning"))],
        },
        kvList(
          [
            { label: "Bucket Versioning", value: versioning === "Enabled" ? onOff(true) : versioning === "Suspended" ? h("span", {}, "Suspended") : onOff(false) },
            { label: "Multi-factor authentication (MFA) delete", value: info.mfaDelete === "Enabled" ? "Enabled" : "Disabled" },
          ],
          { columns: 2 },
        ),
      ),
      container(
        {
          title: "Tags",
          counter: tagRows.length,
          description: "You can use bucket tags to track storage cost or other criteria.",
          actions: [editButton(editHref(bucket, "tags"))],
        },
        tagsTbl.el,
      ),
      container(
        {
          title: "Object Lock",
          description: "Store objects using a write-once-read-many (WORM) model to help you prevent objects from being deleted or overwritten for a fixed amount of time or indefinitely.",
          actions: [editButton(editHref(bucket, "object-lock"))],
        },
        lock.enabled
          ? kvList([
              { label: "Object Lock", value: onOff(true) },
              { label: "Default retention", value: lock.mode ? onOff(true) : onOff(false) },
              lock.mode ? { label: "Default retention mode", value: lock.mode === "COMPLIANCE" ? "Compliance" : "Governance" } : null,
              lock.mode ? { label: "Default retention period", value: lock.years ? `${lock.years} years` : `${lock.days} days` } : null,
            ])
          : h(
              "div",
              { class: "stack-sm" },
              kvList([{ label: "Object Lock", value: onOff(false) }], { columns: 1 }),
              h("p", { class: "muted small" }, versioning === "Enabled" ? "Object Lock can be enabled because Bucket Versioning is enabled. Once enabled, it cannot be disabled." : "Object Lock works only in versioned buckets: enable Bucket Versioning first."),
            ),
      ),
      container(
        {
          title: "Static website hosting",
          description: "Use this bucket to host a website or redirect requests.",
          actions: [editButton(editHref(bucket, "website"))],
        },
        site.enabled
          ? kvList([
              { label: "Static website hosting", value: onOff(true) },
              { label: "Hosting type", value: site.mode === "redirect" ? "Redirect requests for an object" : "Bucket hosting" },
              site.mode === "redirect"
                ? { label: "Redirect to", value: `${site.protocol ? site.protocol + "://" : ""}${site.host}` }
                : { label: "Index document", value: site.index },
              { label: "Bucket website endpoint", value: endpoints },
            ])
          : kvList([{ label: "Static website hosting", value: onOff(false) }], { columns: 1 }),
      ),
    ),
  );
}
