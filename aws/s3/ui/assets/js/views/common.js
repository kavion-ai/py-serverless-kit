// Helpers shared by the views: links, breadcrumbs, bucket info loading, access badges, error pages.

import { h } from "../core/dom.js";
import { api, errorText } from "../core/api.js";
import { href, seg } from "../core/router.js";
import { accessOf, ACCESS_TEXT, bucketArn, ownershipOf } from "../core/s3.js";
import { badge } from "../components/badge.js";
import { alert } from "../components/alert.js";
import { button } from "../components/button.js";
import { setPage } from "./shell.js";

export const bucketPath = (bucket, rest = "") => `/buckets/${seg(bucket)}${rest}`;
export const bucketHref = (bucket, query) => href(bucketPath(bucket), query);
export const objectHref = (bucket, key, versionId, tab) => href(bucketPath(bucket, "/object"), { key, versionId, tab });
export const editHref = (bucket, setting, query) => href(bucketPath(bucket, `/edit/${setting}`), query);
export const objectEditHref = (bucket, what, key, versionId) => href(bucketPath(bucket, `/object/edit/${what}`), { key, versionId });

export function rootCrumbs() {
  return [
    { label: "Object Storage", href: "#/buckets" },
    { label: "Buckets", href: "#/buckets" },
  ];
}

/** Buckets > bucket > folder > folder [> extra...] */
export function bucketCrumbs(bucket, prefix = "", ...extra) {
  const items = [...rootCrumbs(), { label: bucket, href: bucketHref(bucket) }];
  const parts = prefix ? prefix.replace(/\/$/, "").split("/") : [];
  parts.forEach((p, i) => {
    items.push({ label: p || "/", href: bucketHref(bucket, { prefix: parts.slice(0, i + 1).join("/") + "/" }) });
  });
  return items.concat(extra);
}

/** BucketInfo, with the newer fields filled in when the server does not send them yet. */
export async function loadBucketInfo(bucket) {
  const info = await api("BucketInfo", { bucket });
  info.arn = info.arn || bucketArn(info.name);
  info.ownership = ownershipOf(info);
  info.access = accessOf(info);
  info.account = info.account || "000000000000";
  info.websiteHosts = info.websiteHosts || [];
  info.configs = info.configs || {};
  info.tags = info.tags || {};
  info.publicBlock = info.publicBlock || { BlockPublicAcls: false, IgnorePublicAcls: false, BlockPublicPolicy: false, RestrictPublicBuckets: false };
  return info;
}

export function accessBadge(access) {
  if (access === "public") return badge("warning", ACCESS_TEXT.public);
  return h("span", { class: "access-text" }, ACCESS_TEXT[access] || ACCESS_TEXT["objects-can-be-public"]);
}

/** A whole-page error (the bucket or object could not be loaded). */
export function showLoadError(e, crumbs, title = "Something went wrong") {
  setPage({
    crumbs,
    title,
    content: h(
      "div",
      { class: "stack" },
      alert({ type: "error", title }, errorText(e)),
      h("div", {}, button({ label: "Go to buckets", href: "#/buckets" })),
    ),
  });
}

/** Enabled / Disabled status text. */
export function onOff(on, onText = "Enabled", offText = "Disabled") {
  return on ? badge("success", onText) : badge("stopped", offText);
}

/** Navigation shortcut: "Edit" button for a container. */
export function editButton(target, label = "Edit") {
  return button({ label, href: target });
}
