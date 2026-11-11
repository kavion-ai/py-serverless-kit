// The bucket page: header + tabs Objects | Properties | Permissions | Management (?tab=..., ?prefix=...).

import { h } from "../core/dom.js";
import { navigate } from "../core/router.js";
import { tabs } from "../components/tabs.js";
import { loading } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { setPage } from "./shell.js";
import { bucketCrumbs, bucketPath, loadBucketInfo, showLoadError, accessBadge } from "./common.js";
import { renderObjectsTab } from "./objects.js";
import { renderPropertiesTab } from "./properties.js";
import { renderPermissionsTab } from "./permissions.js";
import { renderManagementTab } from "./management.js";

const TABS = [
  { id: "objects", label: "Objects" },
  { id: "properties", label: "Properties" },
  { id: "permissions", label: "Permissions" },
  { id: "management", label: "Management" },
];

export async function render(ctx) {
  const bucket = ctx.params.bucket;
  const tab = TABS.some((t) => t.id === ctx.query.tab) ? ctx.query.tab : "objects";
  const prefix = tab === "objects" ? ctx.query.prefix || "" : "";
  const crumbs = bucketCrumbs(bucket, prefix);
  setPage({ crumbs, title: bucket, content: loading() });
  let info;
  try {
    info = await loadBucketInfo(bucket);
  } catch (e) {
    if (ctx.alive()) showLoadError(e, crumbs, e.code === "NoSuchBucket" ? "The bucket does not exist" : "The bucket could not be loaded");
    return;
  }
  if (!ctx.alive()) return;
  const body = h("div", { class: "tab-body" });
  const titleText = prefix ? prefix.replace(/\/$/, "").split("/").pop() + "/" : bucket;
  setPage({
    crumbs,
    title: titleText,
    content: h(
      "div",
      { class: "stack" },
      pageHeader({
        title: titleText,
        extra: prefix
          ? null
          : h("div", { class: "page-header__meta" }, h("span", {}, `Region ${info.region}`), h("span", { class: "dot" }, "·"), accessBadge(info.access)),
      }),
      tabs({
        tabs: TABS,
        active: tab,
        ariaLabel: "Bucket",
        onChange: (id) => navigate(bucketPath(bucket), { tab: id === "objects" ? "" : id }),
      }),
      body,
    ),
  });
  const args = { ctx, bucket, info, body, prefix };
  if (tab === "objects") await renderObjectsTab(args);
  else if (tab === "properties") renderPropertiesTab(args);
  else if (tab === "permissions") renderPermissionsTab(args);
  else await renderManagementTab(args);
}
